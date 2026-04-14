"""
Project Gutenberg Full-Text Ingestion Pipeline.

Searches Project Gutenberg (via Gutendex API) for our canonical works.
Downloads plain-text versions of public-domain books.
Runs full-text analysis with Haiku (using ANALYSIS_PROMPT_FULL_TEXT).
Updates canonical papers with full_text + deep analysis.

100% legal — Gutenberg works are all public domain with explicit license.

Usage:
  python -m backend.pipeline.seed_gutenberg --budget 10
  python -m backend.pipeline.seed_gutenberg --budget 10 --only-stubs  # focus on stubs first
"""

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone

import httpx
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_API = "https://api.anthropic.com/v1/messages"

HAIKU_INPUT = 0.80 / 1_000_000
HAIKU_OUTPUT = 4.0 / 1_000_000
CONCURRENCY = 5
MAX_CHARS = 80_000  # truncation for Haiku context

budget_spent = 0.0
budget_limit = 10.0
_lock = None

HEADERS_SUPABASE = {
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

from backend.prompts.paper_analysis import ANALYSIS_PROMPT_FULL_TEXT
from backend.pipeline.claim_builder import build_claim_row


async def supabase_get(client, table, params):
    r = await client.get(
        f"{SUPABASE_URL}/rest/v1/{table}", params=params,
        headers={**HEADERS_SUPABASE, "Prefer": ""}, timeout=15,
    )
    return r.json() if r.status_code == 200 else []


async def supabase_post(client, table, data):
    r = await client.post(
        f"{SUPABASE_URL}/rest/v1/{table}",
        json=data, headers=HEADERS_SUPABASE, timeout=15,
    )
    if r.status_code in (200, 201):
        return r.json()
    return None


async def supabase_patch(client, table, params, data):
    r = await client.patch(
        f"{SUPABASE_URL}/rest/v1/{table}", params=params,
        json=data, headers=HEADERS_SUPABASE, timeout=15,
    )
    return r.status_code in (200, 204)


def normalize_name(n):
    return re.sub(r"[^a-z0-9\s]", "", n.lower()).strip()


async def get_or_create_concept(client, c):
    norm = normalize_name(c["name"])
    existing = await supabase_get(client, "concepts", {
        "normalized_name": f"eq.{norm}", "select": "id",
    })
    if existing:
        return existing[0]["id"]
    result = await supabase_post(client, "concepts", {
        "name": c["name"], "normalized_name": norm,
        "type": c.get("type", "phenomenon"),
        "definition": c.get("definition"), "confidence": 0.85,
    })
    return result[0]["id"] if result else None


# --- Gutendex search ---

async def search_gutenberg(client, title, author):
    """Search Gutendex (Project Gutenberg API) for a book."""
    query = f"{title} {author}".strip()
    try:
        r = await client.get(
            "https://gutendex.com/books",
            params={"search": query},
            timeout=20,
        )
        if r.status_code != 200:
            return None
        data = r.json()
        results = data.get("results", [])
        if not results:
            return None
        # Pick best match by title similarity
        title_lower = title.lower()
        for book in results[:5]:
            btitle = (book.get("title") or "").lower()
            if any(word in btitle for word in title_lower.split()[:3]):
                return book
        return results[0]
    except Exception:
        return None


async def download_gutenberg_text(client, book):
    """Download the plain-text version of a Gutenberg book."""
    formats = book.get("formats", {})
    # Prefer UTF-8 plain text
    text_url = None
    for mime, url in formats.items():
        if "text/plain" in mime and "utf-8" in mime:
            text_url = url
            break
    if not text_url:
        # Fallback to any plain text
        for mime, url in formats.items():
            if "text/plain" in mime and "zip" not in mime:
                text_url = url
                break
    if not text_url:
        return None

    try:
        r = await client.get(text_url, timeout=60, follow_redirects=True)
        if r.status_code != 200:
            return None
        text = r.text

        # Strip Gutenberg header/footer boilerplate
        start_markers = [
            "*** START OF THIS PROJECT GUTENBERG",
            "*** START OF THE PROJECT GUTENBERG",
            "***START OF THE PROJECT GUTENBERG",
        ]
        end_markers = [
            "*** END OF THIS PROJECT GUTENBERG",
            "*** END OF THE PROJECT GUTENBERG",
            "***END OF THE PROJECT GUTENBERG",
        ]
        for m in start_markers:
            idx = text.find(m)
            if idx > -1:
                text = text[idx:]
                # Skip to end of that line
                nl = text.find("\n")
                if nl > -1:
                    text = text[nl+1:]
                break
        for m in end_markers:
            idx = text.find(m)
            if idx > -1:
                text = text[:idx]
                break

        text = text.strip()
        return text if len(text) > 2000 else None
    except Exception:
        return None


def truncate_smart(text, max_chars=MAX_CHARS):
    """Keep intro + conclusion, drop middle for long texts."""
    if len(text) <= max_chars:
        return text
    half = max_chars // 2
    return text[:half] + "\n\n[...middle sections truncated for analysis...]\n\n" + text[-half:]


# --- Haiku analysis ---

async def analyze_full_text(client, title, author, year, full_text):
    global budget_spent
    async with _lock:
        if budget_spent >= budget_limit:
            return "STOP"

    truncated = truncate_smart(full_text)
    prompt = ANALYSIS_PROMPT_FULL_TEXT.format(
        title=title, authors=author, year=year or 0, full_text=truncated,
    )
    body = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 4000,
        "temperature": 0.2,
        "messages": [{"role": "user", "content": prompt}],
    }
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "content-type": "application/json",
        "anthropic-version": "2023-06-01",
    }
    for _ in range(2):
        try:
            r = await client.post(ANTHROPIC_API, json=body, headers=headers, timeout=180)
            if r.status_code == 429:
                await asyncio.sleep(10)
                continue
            if r.status_code in (402, 529):
                return "STOP"
            r.raise_for_status()
            data = r.json()
            text = data["content"][0]["text"]
            usage = data.get("usage", {})
            cost = usage.get("input_tokens", 0) * HAIKU_INPUT + usage.get("output_tokens", 0) * HAIKU_OUTPUT
            async with _lock:
                budget_spent += cost
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            return json.loads(text.strip())
        except httpx.ReadTimeout:
            continue
        except json.JSONDecodeError:
            return None
        except Exception:
            return None
    return None


async def update_paper_with_full_analysis(client, paper_id, full_text, analysis):
    """Update existing paper with full text + deep analysis."""
    await supabase_patch(client, "papers", {"id": f"eq.{paper_id}"}, {
        "full_text": full_text[:100_000],
        "full_text_source": "project_gutenberg",
        "analysis": json.dumps(analysis),
        "analysis_model": "claude-haiku-4-5-20251001-fulltext",
        "analyzed_at": datetime.now(tz=timezone.utc).isoformat(),
        "is_stub": False,
    })
    # Add concepts/claims from deep analysis
    concept_ids = {}
    for c in analysis.get("concepts", []):
        cid = await get_or_create_concept(client, c)
        if cid:
            concept_ids[c["name"]] = cid
            await supabase_post(client, "paper_concepts", {
                "paper_id": paper_id, "concept_id": cid,
                "novelty_in_paper": c.get("novelty_at_time", "high"),
                "well_established": c.get("well_established", True),
            })
    for cl in analysis.get("claims", []):
        ct = cl.get("claim") or cl.get("claim_text")
        if ct:
            await supabase_post(
                client,
                "claims",
                build_claim_row(paper_id, cl, default_strength="strong", claim_text_override=ct),
            )
    for rel in analysis.get("relationships", []):
        from_id = concept_ids.get(rel.get("from", "")) or await get_or_create_concept(client, {"name": rel["from"], "type": "phenomenon"})
        to_id = concept_ids.get(rel.get("to", "")) or await get_or_create_concept(client, {"name": rel["to"], "type": "phenomenon"})
        if from_id and to_id:
            await supabase_post(client, "relationships", {
                "source_type": "concept", "source_id": from_id,
                "target_type": "concept", "target_id": to_id,
                "relationship_type": rel.get("type", "BUILDS_ON"),
                "confidence": rel.get("confidence", 0.8),
                "explanation": rel.get("explanation"),
                "paper_id": paper_id,
            })


async def process_canonical_paper(client, paper, sem, stats):
    """Try to find & ingest full text for a canonical paper from Gutenberg."""
    if budget_spent >= budget_limit:
        return
    async with sem:
        if budget_spent >= budget_limit:
            return
        title = paper["title"]
        authors_raw = paper.get("authors", "[]")
        try:
            authors_list = json.loads(authors_raw) if isinstance(authors_raw, str) else authors_raw
            author = authors_list[0].get("name", "") if authors_list else ""
        except Exception:
            author = ""

        book = await search_gutenberg(client, title, author)
        if not book:
            stats["not_found"] += 1
            return

        # Found! Check title match quality
        gtitle = (book.get("title") or "").lower()
        if not any(w in gtitle for w in title.lower().split()[:3] if len(w) > 3):
            stats["not_found"] += 1
            return

        text = await download_gutenberg_text(client, book)
        if not text:
            stats["no_text"] += 1
            return

        # Analyze with full text
        year = paper.get("publication_year") or book.get("download_count") or 0
        analysis = await analyze_full_text(client, title, author, year, text)
        if analysis == "STOP":
            return
        if not analysis or isinstance(analysis, str):
            stats["analysis_failed"] += 1
            return

        await update_paper_with_full_analysis(client, paper["id"], text, analysis)
        stats["success"] += 1
        n_c = len(analysis.get("concepts", []))
        n_r = len(analysis.get("relationships", []))
        print(f"  ✓ [{stats['success']}] {title[:50]} — Gutenberg ID {book['id']} ({len(text):,} chars, {n_c}c/{n_r}r) ${budget_spent:.3f}")


async def async_main():
    global budget_limit, _lock

    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--budget", type=float, default=10.0)
    parser.add_argument("--only-stubs", action="store_true", help="Prioritize canonical stubs")
    parser.add_argument("--limit", type=int, default=200)
    args = parser.parse_args()

    budget_limit = args.budget
    _lock = asyncio.Lock()

    # Get canonical papers needing full text
    async with httpx.AsyncClient() as client:
        params = {
            "canonical": "eq.true",
            "full_text": "is.null",
            "select": "id,title,authors,publication_year,canonical_field,is_stub",
            "limit": str(args.limit),
        }
        if args.only_stubs:
            params["is_stub"] = "eq.true"
        papers = await supabase_get(client, "papers", params)

        print(f"\n{'='*60}")
        print(f"GUTENBERG FULL-TEXT INGESTION")
        print(f"Budget: ${budget_limit} | Concurrency: {CONCURRENCY}")
        print(f"Papers to process: {len(papers)}")
        print(f"{'='*60}\n")

        sem = asyncio.Semaphore(CONCURRENCY)
        stats = {"success": 0, "not_found": 0, "no_text": 0, "analysis_failed": 0}

        # Process in batches
        batch_size = CONCURRENCY * 3
        for i in range(0, len(papers), batch_size):
            if budget_spent >= budget_limit:
                print(f"\n*** BUDGET LIMIT ***")
                break
            batch = papers[i:i+batch_size]
            await asyncio.gather(*[process_canonical_paper(client, p, sem, stats) for p in batch])

        print(f"\n{'='*60}")
        print(f"RESULTS:")
        print(f"  Full text ingested: {stats['success']}")
        print(f"  Not on Gutenberg:   {stats['not_found']}")
        print(f"  No text download:   {stats['no_text']}")
        print(f"  Analysis failed:    {stats['analysis_failed']}")
        print(f"  Cost:               ${budget_spent:.3f} / ${budget_limit}")
        print(f"{'='*60}")


def main():
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
