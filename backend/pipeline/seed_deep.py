"""
Deep Seeding Pipeline — Full-text analysis of priority papers.

Fetches full text via Unpaywall/PDF, then re-analyzes with the full-text
prompt for richer concepts, relationships, and claims.

Usage:
  python -m backend.pipeline.seed_deep --budget 30
  python -m backend.pipeline.seed_deep --budget 30 --limit 100
  python -m backend.pipeline.seed_deep --budget 30 --priority-file data/full_text_priority.json
"""

import argparse
import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

import httpx
from dotenv import load_dotenv

load_dotenv()

# --- Config ---

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OPENALEX_EMAIL = os.getenv("OPENALEX_EMAIL", "")
OPENALEX_BASE = "https://api.openalex.org"
ANTHROPIC_API = "https://api.anthropic.com/v1/messages"
UNPAYWALL_BASE = "https://api.unpaywall.org/v2"

HAIKU_INPUT_COST = 0.80 / 1_000_000
HAIKU_OUTPUT_COST = 4.0 / 1_000_000

CONCURRENCY = 5  # lower than abstract seeding — full text = bigger payloads

budget_spent = 0.0
budget_limit = 30.0
papers_analyzed = 0
_budget_lock = None

HEADERS_SUPABASE = {}

def init_supabase_headers():
    global HEADERS_SUPABASE
    HEADERS_SUPABASE = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }

from backend.prompts.paper_analysis import ANALYSIS_PROMPT_FULL_TEXT, ANALYSIS_PROMPT
from backend.pipeline.claim_builder import build_claim_row


# --- HTML / Text helpers ---

def strip_html(html: str) -> str:
    text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    entity_map = {"&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&apos;": "'", "&nbsp;": " "}
    for entity, char in entity_map.items():
        text = text.replace(entity, char)
    text = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_article_text(html: str) -> str:
    for pattern in [
        r"<article[^>]*>(.*?)</article>",
        r'<div[^>]*class="[^"]*(?:article-body|paper-body|full-text|fulltext|main-content|body-content)[^"]*"[^>]*>(.*?)</div>',
        r'<section[^>]*class="[^"]*(?:article|body|content)[^"]*"[^>]*>(.*?)</section>',
    ]:
        match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
        if match:
            return strip_html(match.group(1))
    body_match = re.search(r"<body[^>]*>(.*?)</body>", html, re.DOTALL | re.IGNORECASE)
    if body_match:
        text = strip_html(body_match.group(1))
        if len(text) > 500:
            return text
    text = strip_html(html)
    return text if len(text) > 200 else ""


def truncate_for_haiku(text: str, max_chars: int = 80_000) -> str:
    """Truncate full text to fit within Haiku's context window (~100k tokens).
    80k chars ≈ 20-25k tokens, leaving room for prompt + output."""
    if len(text) <= max_chars:
        return text
    # Keep intro + conclusion — most important parts
    half = max_chars // 2
    return text[:half] + "\n\n[...middle sections truncated...]\n\n" + text[-half:]


# --- Full text fetching ---

async def fetch_full_text_unpaywall(client: httpx.AsyncClient, doi: str) -> str | None:
    """Fetch full text via Unpaywall (open access HTML)."""
    if not OPENALEX_EMAIL or not doi:
        return None
    clean_doi = re.sub(r"^https?://doi\.org/", "", doi)
    try:
        resp = await client.get(
            f"{UNPAYWALL_BASE}/{clean_doi}",
            params={"email": OPENALEX_EMAIL},
            timeout=20,
        )
        if resp.status_code != 200:
            return None

        data = resp.json()
        oa_url = None
        best = data.get("best_oa_location")
        if best:
            oa_url = best.get("url_for_landing_page") or best.get("url")
        if not oa_url:
            for loc in data.get("oa_locations", []):
                url = loc.get("url_for_landing_page") or loc.get("url")
                if url:
                    oa_url = url
                    break
        if not oa_url:
            return None

        await asyncio.sleep(0.5)
        page = await client.get(
            oa_url, timeout=30, follow_redirects=True,
            headers={"User-Agent": f"KorczakAI/1.0 (academic research; mailto:{OPENALEX_EMAIL})"},
        )
        if page.status_code != 200:
            return None
        ct = page.headers.get("content-type", "")
        if "application/pdf" in ct:
            # Try PDF extraction
            try:
                import fitz
                doc = fitz.open(stream=page.content, filetype="pdf")
                text = "\n".join(p.get_text() for p in doc)
                doc.close()
                if len(text) > 1000:
                    return text[:100_000]
            except Exception:
                return None
        if "text/" not in ct and "html" not in ct:
            return None
        text = extract_article_text(page.text)
        return text if len(text) >= 1000 else None
    except Exception as e:
        return None


# --- Supabase (async) ---

async def supabase_get(client: httpx.AsyncClient, table: str, params: dict) -> list:
    resp = await client.get(
        f"{SUPABASE_URL}/rest/v1/{table}",
        params=params,
        headers={**HEADERS_SUPABASE, "Prefer": ""},
        timeout=15,
    )
    return resp.json() if resp.status_code == 200 else []


async def supabase_patch(client: httpx.AsyncClient, table: str, match_params: dict, data: dict) -> bool:
    resp = await client.patch(
        f"{SUPABASE_URL}/rest/v1/{table}",
        params=match_params,
        json=data,
        headers=HEADERS_SUPABASE,
        timeout=15,
    )
    return resp.status_code in (200, 204)


async def supabase_post(client: httpx.AsyncClient, table: str, data: dict) -> dict | None:
    resp = await client.post(
        f"{SUPABASE_URL}/rest/v1/{table}",
        json=data, headers=HEADERS_SUPABASE, timeout=15,
    )
    if resp.status_code in (200, 201):
        return resp.json()
    elif resp.status_code == 409:
        return None
    return None


def normalize_name(name: str) -> str:
    return re.sub(r"[^a-z0-9\s]", "", name.lower()).strip()


async def get_or_create_concept(client: httpx.AsyncClient, concept_data: dict) -> str | None:
    norm = normalize_name(concept_data["name"])
    existing = await supabase_get(client, "concepts", {"normalized_name": f"eq.{norm}", "select": "id"})
    if existing:
        return existing[0]["id"]
    row = {
        "name": concept_data["name"],
        "normalized_name": norm,
        "type": concept_data.get("type", "phenomenon"),
        "definition": concept_data.get("definition"),
        "confidence": 0.7,  # higher confidence for full-text analysis
    }
    result = await supabase_post(client, "concepts", row)
    return result[0]["id"] if result else None


# --- Claude Full-Text Analysis ---

async def analyze_full_text(client: httpx.AsyncClient, title: str, authors: str, year: int, full_text: str) -> dict | None:
    """Analyze paper with full text using Haiku."""
    global budget_spent, papers_analyzed

    async with _budget_lock:
        if budget_spent >= budget_limit:
            return "STOP"

    truncated = truncate_for_haiku(full_text)
    prompt = ANALYSIS_PROMPT_FULL_TEXT.format(
        title=title, authors=authors, year=year, full_text=truncated,
    )

    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "content-type": "application/json",
        "anthropic-version": "2023-06-01",
    }
    body = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 4000,  # more output for full-text analysis
        "temperature": 0.2,
        "messages": [{"role": "user", "content": prompt}],
    }

    for attempt in range(3):
        try:
            resp = await client.post(ANTHROPIC_API, json=body, headers=headers, timeout=120)
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("retry-after", 5))
                await asyncio.sleep(min(retry_after, 30))
                continue
            if resp.status_code in (402, 529):
                return "STOP"

            resp.raise_for_status()
            data = resp.json()
            text = data["content"][0]["text"]

            usage = data.get("usage", {})
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            call_cost = (input_tokens * HAIKU_INPUT_COST) + (output_tokens * HAIKU_OUTPUT_COST)

            async with _budget_lock:
                budget_spent += call_cost
                papers_analyzed += 1

            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            return json.loads(text.strip())

        except httpx.ReadTimeout:
            if attempt < 2:
                continue
            return None
        except json.JSONDecodeError:
            return None
        except Exception:
            return None
    return None


# --- Update paper with deep analysis ---

async def update_paper_deep(client: httpx.AsyncClient, paper_id: str, analysis: dict):
    """Update an existing paper's analysis + add new concepts/claims/relationships."""
    try:
        return await _update_paper_deep_inner(client, paper_id, analysis)
    except Exception as e:
        print(f"    update_paper_deep error: {e}")
        return None


async def _update_paper_deep_inner(client: httpx.AsyncClient, paper_id: str, analysis: dict):
    # Update the paper's analysis
    await supabase_patch(client, "papers", {"id": f"eq.{paper_id}"}, {
        "analysis": json.dumps(analysis),
        "analysis_model": "claude-haiku-4-5-20251001-fulltext",
        "analyzed_at": datetime.now(tz=timezone.utc).isoformat(),
    })

    # Add new concepts (skip existing)
    concept_ids = {}
    for c in analysis.get("concepts", []):
        cid = await get_or_create_concept(client, c)
        if cid:
            concept_ids[c["name"]] = cid
            await supabase_post(client, "paper_concepts", {
                "paper_id": paper_id,
                "concept_id": cid,
                "novelty_in_paper": c.get("novelty_at_time", "low"),
                "well_established": c.get("well_established", True),
            })

    # Add new claims
    for cl in analysis.get("claims", []):
        claim_text = cl.get("claim") or cl.get("claim_text") or cl.get("text")
        if not claim_text:
            continue
        await supabase_post(
            client,
            "claims",
            build_claim_row(paper_id, cl, claim_text_override=claim_text),
        )

    # Add new relationships
    for rel in analysis.get("relationships", []):
        from_id = concept_ids.get(rel.get("from", "")) or await get_or_create_concept(client, {"name": rel["from"], "type": "phenomenon"})
        to_id = concept_ids.get(rel.get("to", "")) or await get_or_create_concept(client, {"name": rel["to"], "type": "phenomenon"})
        if from_id and to_id:
            await supabase_post(client, "relationships", {
                "source_type": "concept", "source_id": from_id,
                "target_type": "concept", "target_id": to_id,
                "relationship_type": rel.get("type", "BUILDS_ON"),
                "confidence": rel.get("confidence", 0.7),
                "explanation": rel.get("explanation"),
                "paper_id": paper_id,
            })


# --- Main pipeline ---

async def deep_seed_existing_papers(client: httpx.AsyncClient, limit: int):
    """Fetch full text and re-analyze the most important papers already in DB."""
    global budget_spent

    print(f"\n{'='*60}")
    print(f"DEEP SEEDING — Full Text Analysis")
    print(f"Budget: ${budget_limit:.2f} | Concurrency: {CONCURRENCY}")
    print(f"{'='*60}")

    # Get top-cited papers that don't have full text yet
    papers = await supabase_get(client, "papers", {
        "select": "id,doi,title,authors,publication_year,abstract,full_text,cited_by_count,openalex_id",
        "doi": "not.is.null",
        "order": "cited_by_count.desc",
        "limit": str(limit),
    })

    print(f"  Found {len(papers)} papers with DOIs (sorted by citations)")

    sem = asyncio.Semaphore(CONCURRENCY)
    stats = {"full_text_fetched": 0, "analyzed": 0, "already_had_text": 0, "no_text": 0, "errors": 0}

    async def process_paper(paper):
        if budget_spent >= budget_limit:
            return

        async with sem:
            if budget_spent >= budget_limit:
                return

            title = paper.get("title", "?")
            doi = paper.get("doi", "")
            paper_id = paper["id"]
            cited = paper.get("cited_by_count", 0)

            # Check if already has full text
            full_text = paper.get("full_text")
            if not full_text:
                # Fetch full text
                full_text = await fetch_full_text_unpaywall(client, doi)
                if full_text:
                    # Save to DB
                    await supabase_patch(client, "papers", {"id": f"eq.{paper_id}"}, {
                        "full_text": full_text[:100_000],
                        "full_text_source": "unpaywall",
                    })
                    stats["full_text_fetched"] += 1
                else:
                    stats["no_text"] += 1
                    return
            else:
                stats["already_had_text"] += 1

            # Analyze with full text
            authors_str = ""
            try:
                authors_list = json.loads(paper.get("authors", "[]"))
                authors_str = ", ".join(a.get("name", "") for a in authors_list[:5])
            except Exception:
                authors_str = "Unknown"

            analysis = await analyze_full_text(
                client, title, authors_str,
                paper.get("publication_year", 0), full_text
            )

            if analysis == "STOP":
                return
            if analysis and not isinstance(analysis, str):
                await update_paper_deep(client, paper_id, analysis)
                stats["analyzed"] += 1
                n_c = len(analysis.get("concepts", []))
                n_r = len(analysis.get("relationships", []))
                print(f"  [{stats['analyzed']}] {title[:55]}... ({n_c}c/{n_r}r) [cited:{cited}] ${budget_spent:.3f}")
            else:
                stats["errors"] += 1

    # Process in batches
    batch_size = CONCURRENCY * 2
    for i in range(0, len(papers), batch_size):
        if budget_spent >= budget_limit:
            print(f"\n*** BUDGET LIMIT REACHED ***")
            break
        batch = papers[i:i + batch_size]
        await asyncio.gather(*[process_paper(p) for p in batch])

    print(f"\n{'='*60}")
    print(f"DEEP SEEDING RESULTS:")
    print(f"  Full text fetched:  {stats['full_text_fetched']}")
    print(f"  Already had text:   {stats['already_had_text']}")
    print(f"  Analyzed (deep):    {stats['analyzed']}")
    print(f"  No text available:  {stats['no_text']}")
    print(f"  Errors:             {stats['errors']}")
    print(f"  Cost:               ${budget_spent:.3f} / ${budget_limit:.2f}")
    print(f"  Rate:               ${budget_spent/max(papers_analyzed,1):.4f}/paper")
    print(f"{'='*60}")


async def deep_seed_priority_list(client: httpx.AsyncClient, priority_file: str):
    """Seed priority papers from the curated list — find in OpenAlex, fetch full text, analyze."""
    global budget_spent

    with open(priority_file) as f:
        data = json.load(f)

    all_works = []
    for field in data.get("papers", []):
        for work in field.get("works", []):
            work["field"] = field["field"]
            all_works.append(work)

    print(f"\n{'='*60}")
    print(f"PRIORITY DEEP SEEDING — {len(all_works)} canonical works")
    print(f"Budget: ${budget_limit:.2f} | Concurrency: {CONCURRENCY}")
    print(f"{'='*60}")

    sem = asyncio.Semaphore(CONCURRENCY)
    stats = {"found": 0, "analyzed": 0, "not_found": 0, "errors": 0}

    async def process_work(work):
        if budget_spent >= budget_limit:
            return

        async with sem:
            if budget_spent >= budget_limit:
                return

            title = work["title"]
            author = work.get("author", "")
            field = work.get("field", "")

            # Search OpenAlex
            try:
                resp = await client.get(f"{OPENALEX_BASE}/works", params={
                    "search": title,
                    "per_page": 3,
                    "select": "id,title,authorships,publication_year,abstract_inverted_index,cited_by_count,doi,primary_location",
                }, timeout=15)
                if resp.status_code != 200:
                    stats["not_found"] += 1
                    return
                results = resp.json().get("results", [])
                if not results:
                    stats["not_found"] += 1
                    print(f"  [NOT FOUND] {title[:50]}")
                    return
            except Exception:
                stats["not_found"] += 1
                return

            raw = results[0]
            oa_id = raw.get("id", "").split("/")[-1]
            doi = raw.get("doi")
            year = raw.get("publication_year", work.get("year", 0))

            # Reconstruct abstract
            inv_idx = raw.get("abstract_inverted_index")
            abstract = ""
            if inv_idx:
                word_positions = []
                for word, positions in inv_idx.items():
                    for pos in positions:
                        word_positions.append((pos, word))
                word_positions.sort()
                abstract = " ".join(w for _, w in word_positions)

            # Check if already in DB
            existing = await supabase_get(client, "papers", {
                "openalex_id": f"eq.{oa_id}", "select": "id,full_text",
            })

            # Try to get full text
            full_text = None
            paper_id = None

            if existing:
                paper_id = existing[0]["id"]
                full_text = existing[0].get("full_text")

            if not full_text and doi:
                full_text = await fetch_full_text_unpaywall(client, doi)
                if full_text and paper_id:
                    await supabase_patch(client, "papers", {"id": f"eq.{paper_id}"}, {
                        "full_text": full_text[:100_000],
                        "full_text_source": "unpaywall",
                    })

            # Use full text or abstract
            text_for_analysis = full_text or abstract
            if not text_for_analysis or len(text_for_analysis) < 50:
                stats["not_found"] += 1
                return

            stats["found"] += 1

            # Choose prompt based on text length
            authors_list = raw.get("authorships", [])
            authors_str = ", ".join(
                a.get("author", {}).get("display_name", "") for a in authors_list[:5]
            ) or author

            if full_text and len(full_text) > 1000:
                analysis = await analyze_full_text(client, title, authors_str, year, full_text)
            else:
                # Fall back to abstract analysis
                analysis = await analyze_full_text(client, title, authors_str, year, abstract)

            if analysis == "STOP":
                return
            if analysis and not isinstance(analysis, str):
                if paper_id:
                    await update_paper_deep(client, paper_id, analysis)
                else:
                    # Insert new paper
                    paper_row = {
                        "openalex_id": oa_id,
                        "doi": doi,
                        "title": raw.get("title", title),
                        "authors": json.dumps([{"name": a.get("author", {}).get("display_name", "")}
                                               for a in authors_list[:10]]),
                        "publication_year": year,
                        "abstract": abstract,
                        "full_text": (full_text or "")[:100_000] if full_text else None,
                        "full_text_source": "unpaywall" if full_text else None,
                        "cited_by_count": raw.get("cited_by_count", 0),
                        "analysis": json.dumps(analysis),
                        "analysis_model": "claude-haiku-4-5-20251001-fulltext" if full_text else "claude-haiku-4-5-20251001",
                        "analyzed_at": datetime.now(tz=timezone.utc).isoformat(),
                    }
                    pt = analysis.get("paper_type", {})
                    paper_row["paper_type"] = pt.get("type")
                    paper_row["subfield"] = pt.get("subfield")
                    result = await supabase_post(client, "papers", paper_row)
                    if result:
                        paper_id = result[0]["id"]
                        # Insert concepts/claims/relationships
                        await update_paper_deep(client, paper_id, analysis)

                stats["analyzed"] += 1
                src = "FULL" if full_text else "ABSTRACT"
                n_c = len(analysis.get("concepts", []))
                n_r = len(analysis.get("relationships", []))
                print(f"  [{stats['analyzed']}] [{src}] {title[:50]}... ({n_c}c/{n_r}r) ${budget_spent:.3f}")
            else:
                stats["errors"] += 1

    # Process all works
    batch_size = CONCURRENCY * 2
    for i in range(0, len(all_works), batch_size):
        if budget_spent >= budget_limit:
            break
        batch = all_works[i:i + batch_size]
        await asyncio.gather(*[process_work(w) for w in batch])

    print(f"\n{'='*60}")
    print(f"PRIORITY DEEP SEEDING RESULTS:")
    print(f"  Found & processed:  {stats['found']}")
    print(f"  Deep analyzed:      {stats['analyzed']}")
    print(f"  Not found:          {stats['not_found']}")
    print(f"  Errors:             {stats['errors']}")
    print(f"  Cost:               ${budget_spent:.3f} / ${budget_limit:.2f}")
    print(f"{'='*60}")


# --- Main ---

async def async_main():
    global budget_limit, _budget_lock

    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Deep seeding: full-text paper analysis")
    parser.add_argument("--budget", type=float, default=30.0, help="Max budget in USD")
    parser.add_argument("--limit", type=int, default=200, help="Max papers to process")
    parser.add_argument("--priority-file", type=str, help="Path to priority papers JSON")
    parser.add_argument("--top-cited", action="store_true", help="Deep-analyze top-cited papers in DB")
    args = parser.parse_args()

    budget_limit = args.budget
    _budget_lock = asyncio.Lock()

    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        print("ERROR: Set SUPABASE_URL and SUPABASE_SERVICE_KEY in .env")
        sys.exit(1)
    if not ANTHROPIC_API_KEY:
        print("ERROR: Set ANTHROPIC_API_KEY in .env")
        sys.exit(1)

    init_supabase_headers()

    async with httpx.AsyncClient() as client:
        if args.priority_file:
            await deep_seed_priority_list(client, args.priority_file)
        elif args.top_cited:
            await deep_seed_existing_papers(client, args.limit)
        else:
            # Default: priority list first, then top-cited
            priority_path = os.path.join(os.path.dirname(__file__), "..", "..", "data", "full_text_priority.json")
            if os.path.exists(priority_path):
                await deep_seed_priority_list(client, priority_path)
            # If budget remains, do top-cited
            if budget_spent < budget_limit:
                remaining_budget = budget_limit - budget_spent
                print(f"\n  Remaining budget: ${remaining_budget:.2f} — switching to top-cited papers")
                await deep_seed_existing_papers(client, args.limit)


def main():
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
