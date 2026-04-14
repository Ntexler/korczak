"""
Optimized Graph Seeding Pipeline — Haiku-first with syllabus-driven discovery.

3 modes:
  1. --domain: Seed from OpenAlex by topic (same as seed_graph but 70% cheaper with Haiku)
  2. --syllabus: Pull readings from syllabi sources → find in OpenAlex → analyze
  3. --all-fields: Seed all 28 core fields from OpenAlex

Cost: ~$0.009/paper (Haiku) vs ~$0.03/paper (Sonnet)

Usage:
  python -m backend.pipeline.seed_optimized --domain anthropology --limit 500
  python -m backend.pipeline.seed_optimized --domain anthropology --limit 2500 --budget 30
  python -m backend.pipeline.seed_optimized --syllabus --sources mit_ocw,open_syllabus
  python -m backend.pipeline.seed_optimized --all-fields --limit 500 --budget 200
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
OPENALEX_BASE = "https://api.openalex.org"
ANTHROPIC_API = "https://api.anthropic.com/v1/messages"

# Haiku pricing (70% cheaper than Sonnet)
HAIKU_INPUT_COST = 0.80 / 1_000_000
HAIKU_OUTPUT_COST = 4.0 / 1_000_000
SONNET_INPUT_COST = 3.0 / 1_000_000
SONNET_OUTPUT_COST = 15.0 / 1_000_000

# Concurrency: 10 parallel Claude API calls
CONCURRENCY = 10

def _set_concurrency(n: int):
    global CONCURRENCY
    CONCURRENCY = n

budget_spent = 0.0
budget_limit = 50.0
papers_analyzed = 0
_budget_lock = None  # initialized in async context

# Supabase REST helpers
HEADERS_SUPABASE = {}

def init_supabase_headers():
    global HEADERS_SUPABASE
    HEADERS_SUPABASE = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }

# OpenAlex subfield/field IDs (numeric only — broad disciplines)
# Filter: topics.subfield.id:<num> or topics.field.id:<num>
DOMAINS = {
    # Humanities
    "philosophy": {"subfield_id": "1211", "label": "Philosophy"},
    "history": {"subfield_id": "1202", "label": "History"},
    "linguistics": {"subfield_id": "1203", "label": "Language & Linguistics"},
    "religious_studies": {"subfield_id": "1212", "label": "Religious Studies"},
    # Social Sciences
    "anthropology": {"subfield_id": "3314", "label": "Anthropology"},
    "sociology": {"subfield_id": "3312", "label": "Sociology & Political Science"},
    "political_science": {"subfield_id": "3320", "label": "Political Science & Intl Relations"},
    "economics": {"subfield_id": "2002", "label": "Economics & Econometrics"},
    "education": {"subfield_id": "3304", "label": "Education"},
    "law": {"subfield_id": "3308", "label": "Law"},
    "geography": {"subfield_id": "3305", "label": "Geography & Development"},
    "gender_studies": {"subfield_id": "3318", "label": "Gender Studies"},
    # Psychology & Cognitive
    "psychology": {"field_id": "32", "label": "Psychology"},
    "cognitive_neuroscience": {"subfield_id": "2805", "label": "Cognitive Neuroscience"},
    # Sciences
    "neuroscience": {"field_id": "28", "label": "Neuroscience"},
    "biology": {"subfield_id": "1307", "label": "Cell Biology"},
    "physics": {"field_id": "31", "label": "Physics & Astronomy"},
    "mathematics": {"field_id": "26", "label": "Mathematics"},
    "computer_science": {"field_id": "17", "label": "Computer Science"},
    "environmental_science": {"field_id": "23", "label": "Environmental Science"},
    "medicine": {"field_id": "27", "label": "Medicine"},
    # Business & Media
    "business": {"subfield_id": "1403", "label": "Business & Management"},
    "media_studies": {"subfield_id": "3315", "label": "Library & Information Sciences"},
    # Sleep (keep original topic — it was correct)
    "sleep": {"topic_id": "https://openalex.org/T10985", "label": "Sleep & Cognition"},
}

# Top high-impact journals (use --journals mode)
TOP_JOURNALS = {
    "nature": {"source_id": "S137773608", "label": "Nature"},
    "science": {"source_id": "S3880285", "label": "Science"},
    "cell": {"source_id": "S110447773", "label": "Cell"},
    "pnas": {"source_id": "S125754415", "label": "PNAS"},
    "lancet": {"source_id": "S49861241", "label": "The Lancet"},
    "nejm": {"source_id": "S62468778", "label": "NEJM"},
    "nature_medicine": {"source_id": "S203256638", "label": "Nature Medicine"},
    "nature_neuroscience": {"source_id": "S2298632", "label": "Nature Neuroscience"},
    "nature_physics": {"source_id": "S156274416", "label": "Nature Physics"},
    "nature_chemistry": {"source_id": "S202193212", "label": "Nature Chemistry"},
    "nature_genetics": {"source_id": "S137905309", "label": "Nature Genetics"},
    "nature_communications": {"source_id": "S64187185", "label": "Nature Communications"},
}

from backend.prompts.paper_analysis import ANALYSIS_PROMPT
from backend.pipeline.claim_builder import build_claim_row


# --- OpenAlex ---

async def fetch_openalex_page(client: httpx.AsyncClient, domain: dict, per_page: int = 50, cursor: str = "*") -> dict:
    # Build filter based on whether we have a topic_id, subfield_id, field_id, or source_id
    if "source_id" in domain:
        filter_prefix = f"primary_location.source.id:{domain['source_id']}"
    elif "topic_id" in domain:
        filter_prefix = f"topics.id:{domain['topic_id']}"
    elif "subfield_id" in domain:
        filter_prefix = f"primary_topic.subfield.id:{domain['subfield_id']}"
    else:
        filter_prefix = f"primary_topic.field.id:{domain['field_id']}"

    params = {
        "filter": (
            f"{filter_prefix},"
            "has_abstract:true,language:en,type:article,"
            "from_publication_date:2010-01-01"
        ),
        "sort": "cited_by_count:desc",
        "per_page": per_page,
        "cursor": cursor,
        "select": (
            "id,title,authorships,publication_year,abstract_inverted_index,"
            "cited_by_count,doi,primary_location,topics"
        ),
    }
    email = os.getenv("OPENALEX_EMAIL")
    if email:
        params["mailto"] = email
    resp = await client.get(f"{OPENALEX_BASE}/works", params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


async def search_openalex_by_title(client: httpx.AsyncClient, title: str) -> dict | None:
    """Search OpenAlex by paper title. Returns first match or None."""
    params = {
        "search": title,
        "per_page": 3,
        "select": (
            "id,title,authorships,publication_year,abstract_inverted_index,"
            "cited_by_count,doi,primary_location,topics"
        ),
    }
    email = os.getenv("OPENALEX_EMAIL")
    if email:
        params["mailto"] = email
    try:
        resp = await client.get(f"{OPENALEX_BASE}/works", params=params, timeout=15)
        if resp.status_code == 200:
            results = resp.json().get("results", [])
            if results:
                return results[0]
    except Exception:
        pass
    return None


def reconstruct_abstract(inverted_index: dict | None) -> str:
    if not inverted_index:
        return ""
    word_positions = []
    for word, positions in inverted_index.items():
        for pos in positions:
            word_positions.append((pos, word))
    word_positions.sort()
    return " ".join(w for _, w in word_positions)


def extract_authors(authorships: list) -> list[dict]:
    authors = []
    for a in authorships:
        author = a.get("author", {})
        inst = (
            a.get("institutions", [{}])[0].get("display_name")
            if a.get("institutions")
            else None
        )
        author_id = author.get("id") or ""
        authors.append({
            "name": author.get("display_name", "Unknown"),
            "openalex_id": author_id.split("/")[-1] if author_id else "",
            "orcid": author.get("orcid"),
            "institution": inst,
        })
    return authors


def normalize_paper(raw: dict) -> dict:
    return {
        "openalex_id": raw.get("id", "").split("/")[-1],
        "title": raw.get("title", ""),
        "authors": extract_authors(raw.get("authorships", [])),
        "publication_year": raw.get("publication_year"),
        "abstract": reconstruct_abstract(raw.get("abstract_inverted_index")),
        "doi": raw.get("doi"),
        "cited_by_count": raw.get("cited_by_count", 0),
        "source_journal": (
            (raw.get("primary_location") or {}).get("source") or {}
        ).get("display_name"),
    }


# --- Claude Analysis (Haiku-first, async) ---

async def analyze_paper_haiku(client: httpx.AsyncClient, title: str, authors_str: str, year: int, abstract: str) -> dict | None:
    """Analyze with Haiku (70% cheaper). Same prompt, lighter model. Async."""
    global budget_spent, papers_analyzed

    if not abstract or len(abstract) < 50:
        return None

    async with _budget_lock:
        if budget_spent >= budget_limit:
            print(f"\n*** BUDGET LIMIT REACHED (${budget_spent:.2f} / ${budget_limit:.2f}) ***")
            return "STOP"

    prompt = ANALYSIS_PROMPT.format(
        title=title, authors=authors_str, year=year, abstract=abstract,
    )
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "content-type": "application/json",
        "anthropic-version": "2023-06-01",
    }
    body = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 2000,
        "temperature": 0.2,
        "messages": [{"role": "user", "content": prompt}],
    }

    for attempt in range(3):
        try:
            resp = await client.post(ANTHROPIC_API, json=body, headers=headers, timeout=60)

            if resp.status_code == 429:
                retry_after = int(resp.headers.get("retry-after", 5))
                await asyncio.sleep(min(retry_after, 30))
                continue
            if resp.status_code in (402, 529):
                print(f"\n*** CREDITS EXHAUSTED (HTTP {resp.status_code}) ***")
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

        except httpx.HTTPStatusError as e:
            if e.response.status_code in (402, 529):
                return "STOP"
            print(f"    Analysis error: {e}")
            return None
        except httpx.ReadTimeout:
            if attempt < 2:
                continue
            print(f"    Timeout — skipping")
            return None
        except json.JSONDecodeError:
            print(f"    JSON parse error — skipping")
            return None
        except Exception as e:
            print(f"    Analysis error: {e}")
            return None
    return None


# --- Supabase (async) ---

async def supabase_post(client: httpx.AsyncClient, table: str, data: dict | list) -> dict | list | None:
    resp = await client.post(
        f"{SUPABASE_URL}/rest/v1/{table}",
        json=data, headers=HEADERS_SUPABASE, timeout=15,
    )
    if resp.status_code in (200, 201):
        return resp.json()
    elif resp.status_code == 409:
        return None
    else:
        print(f"    DB error ({table}): {resp.status_code} {resp.text[:150]}")
        return None


async def supabase_get(client: httpx.AsyncClient, table: str, params: dict) -> list:
    resp = await client.get(
        f"{SUPABASE_URL}/rest/v1/{table}",
        params=params,
        headers={**HEADERS_SUPABASE, "Prefer": ""},
        timeout=15,
    )
    return resp.json() if resp.status_code == 200 else []


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
        "confidence": 0.5,
    }
    result = await supabase_post(client, "concepts", row)
    return result[0]["id"] if result else None


async def insert_paper_and_analysis(client: httpx.AsyncClient, paper: dict, analysis: dict, model_name: str = "claude-haiku-4-5-20251001") -> str | None:
    try:
        paper_type = analysis.get("paper_type") or {}
        paper_row = {
            "openalex_id": paper["openalex_id"],
            "doi": paper.get("doi"),
            "title": paper["title"],
            "authors": json.dumps(paper["authors"]),
            "publication_year": paper["publication_year"],
            "abstract": paper["abstract"],
            "paper_type": paper_type.get("type"),
            "subfield": paper_type.get("subfield"),
            "source_journal": paper.get("source_journal"),
            "cited_by_count": paper["cited_by_count"],
            "analysis": json.dumps(analysis),
            "analysis_model": model_name,
            "analyzed_at": datetime.now(tz=timezone.utc).isoformat(),
        }

        result = await supabase_post(client, "papers", paper_row)
        if not result:
            return None
        paper_id = result[0]["id"]

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

        for cl in analysis.get("claims", []):
            await supabase_post(client, "claims", build_claim_row(paper_id, cl))

        for rel in analysis.get("relationships", []):
            from_id = concept_ids.get(rel.get("from", "")) or await get_or_create_concept(client, {"name": rel["from"], "type": "phenomenon"})
            to_id = concept_ids.get(rel.get("to", "")) or await get_or_create_concept(client, {"name": rel["to"], "type": "phenomenon"})
            if from_id and to_id:
                await supabase_post(client, "relationships", {
                    "source_type": "concept", "source_id": from_id,
                    "target_type": "concept", "target_id": to_id,
                    "relationship_type": rel.get("type", "BUILDS_ON"),
                    "confidence": rel.get("confidence", 0.5),
                    "explanation": rel.get("explanation"),
                    "paper_id": paper_id,
                })

        return paper_id
    except Exception as e:
        print(f"    Insert error: {e}")
        return None


async def paper_exists(client: httpx.AsyncClient, openalex_id: str) -> bool:
    return bool(await supabase_get(client, "papers", {"openalex_id": f"eq.{openalex_id}", "select": "id"}))


# --- Mode 1: Domain Seeding (Haiku, async with concurrency) ---

async def _process_one_paper(client: httpx.AsyncClient, sem: asyncio.Semaphore, paper: dict, counters: dict, limit: int):
    """Process a single paper: analyze with Haiku, insert into DB."""
    if counters["inserted"] >= limit or budget_spent >= budget_limit:
        return

    async with sem:
        if counters["inserted"] >= limit or budget_spent >= budget_limit:
            return

        authors_str = ", ".join(a["name"] for a in paper["authors"][:5])
        analysis = await analyze_paper_haiku(client, paper["title"], authors_str, paper["publication_year"], paper["abstract"])

        if analysis == "STOP":
            counters["stop"] = True
            return
        if analysis and not isinstance(analysis, str):
            pid = await insert_paper_and_analysis(client, paper, analysis)
            if pid:
                counters["inserted"] += 1
                n_c = len(analysis.get("concepts", []))
                if counters["inserted"] % 10 == 0 or counters["inserted"] <= 5:
                    print(f"  [{counters['inserted']}/{limit}] {paper['title'][:50]}... ({n_c} concepts) ${budget_spent:.3f}")
            else:
                counters["errors"] += 1
        else:
            counters["errors"] += 1


async def seed_domain(client: httpx.AsyncClient, domain_key: str, limit: int):
    domain = DOMAINS.get(domain_key) or TOP_JOURNALS.get(domain_key)
    print(f"\n{'='*60}")
    print(f"SEEDING: {domain['label']} (Haiku x{CONCURRENCY})")
    print(f"Target: {limit} papers | Budget: ${budget_limit:.2f}")
    print(f"{'='*60}")

    sem = asyncio.Semaphore(CONCURRENCY)
    cursor = "*"
    counters = {"inserted": 0, "skipped": 0, "errors": 0, "consecutive_skips": 0, "stop": False}

    while counters["inserted"] < limit and not counters["stop"]:
        if budget_spent >= budget_limit:
            print(f"\n*** BUDGET LIMIT ***")
            break

        try:
            data = await fetch_openalex_page(client, domain, min(50, limit - counters["inserted"] + 10), cursor)
        except Exception as e:
            print(f"  OpenAlex error: {e}")
            break

        results = data.get("results", [])
        cursor = data.get("meta", {}).get("next_cursor")
        if not results or not cursor:
            print("  No more results")
            break

        # Filter papers that need processing
        batch = []
        for raw in results:
            if counters["inserted"] + len(batch) >= limit or budget_spent >= budget_limit:
                break

            paper = normalize_paper(raw)
            if await paper_exists(client, paper["openalex_id"]):
                counters["skipped"] += 1
                counters["consecutive_skips"] += 1
                if counters["consecutive_skips"] >= 200:
                    print(f"  200 consecutive skips — moving on")
                    print(f"\n  Done: {counters['inserted']} inserted, {counters['skipped']} skipped, {counters['errors']} errors, ${budget_spent:.3f}")
                    return counters["inserted"]
                continue

            if not paper["abstract"] or len(paper["abstract"]) < 50:
                counters["skipped"] += 1
                continue

            counters["consecutive_skips"] = 0
            batch.append(paper)

        # Process batch concurrently
        if batch:
            tasks = [_process_one_paper(client, sem, p, counters, limit) for p in batch]
            await asyncio.gather(*tasks)

    print(f"\n  Done: {counters['inserted']} inserted, {counters['skipped']} skipped, {counters['errors']} errors, ${budget_spent:.3f}")
    return counters["inserted"]


# --- Mode 2: Syllabus-Driven Discovery (async) ---

async def _process_one_syllabus_reading(client: httpx.AsyncClient, sem: asyncio.Semaphore, reading: dict, counters: dict):
    """Process a single syllabus reading concurrently."""
    if budget_spent >= budget_limit or counters.get("stop"):
        return

    title = reading.get("external_title", "")
    doi = reading.get("external_doi")
    if not title and not doi:
        return

    async with sem:
        if budget_spent >= budget_limit:
            return

        # Try to find in OpenAlex
        raw = None
        if doi:
            try:
                resp = await client.get(f"{OPENALEX_BASE}/works/doi:{doi}", timeout=10)
                if resp.status_code == 200:
                    raw = resp.json()
            except Exception:
                pass

        if not raw and title:
            raw = await search_openalex_by_title(client, title)

        if not raw:
            counters["not_found"] += 1
            idx = counters["not_found"] + counters["inserted"] + counters["matched"]
            if idx <= 10 or idx % 50 == 0:
                print(f"  Not found: {title[:50]}...")
            return

        paper = normalize_paper(raw)

        if await paper_exists(client, paper["openalex_id"]):
            existing = await supabase_get(client, "papers", {
                "openalex_id": f"eq.{paper['openalex_id']}",
                "select": "id",
            })
            if existing:
                await client.patch(
                    f"{SUPABASE_URL}/rest/v1/syllabus_readings?id=eq.{reading['id']}",
                    json={"paper_id": existing[0]["id"], "match_confidence": 0.9},
                    headers=HEADERS_SUPABASE,
                    timeout=10,
                )
                counters["matched"] += 1
            return

        if not paper["abstract"] or len(paper["abstract"]) < 50:
            counters["not_found"] += 1
            return

        authors_str = ", ".join(a["name"] for a in paper["authors"][:5])
        analysis = await analyze_paper_haiku(client, paper["title"], authors_str, paper["publication_year"], paper["abstract"])

        if analysis == "STOP":
            counters["stop"] = True
            return
        if analysis and not isinstance(analysis, str):
            pid = await insert_paper_and_analysis(client, paper, analysis)
            if pid:
                counters["inserted"] += 1
                await client.patch(
                    f"{SUPABASE_URL}/rest/v1/syllabus_readings?id=eq.{reading['id']}",
                    json={"paper_id": pid, "match_confidence": 0.95},
                    headers=HEADERS_SUPABASE,
                    timeout=10,
                )
                if counters["inserted"] % 10 == 0 or counters["inserted"] <= 5:
                    print(f"  [{counters['inserted']}] {paper['title'][:50]}... ${budget_spent:.3f}")


async def seed_from_syllabi(client: httpx.AsyncClient, sources: list[str]):
    """Pull readings from existing syllabi, find them in OpenAlex, analyze with Haiku."""
    print(f"\n{'='*60}")
    print(f"SYLLABUS-DRIVEN SEEDING (x{CONCURRENCY} concurrency)")
    print(f"Sources: {', '.join(sources)}")
    print(f"{'='*60}")

    readings = await supabase_get(client, "syllabus_readings", {
        "paper_id": "is.null",
        "select": "id,external_title,external_authors,external_doi,external_year,syllabus_id",
        "limit": "500",
    })

    if not readings:
        print("  No unmatched readings found. Run scrapers first:")
        print("    python -m backend.pipeline.scrape_mit_ocw")
        print("    python -m backend.pipeline.scrape_open_syllabus")
        return 0

    print(f"  Found {len(readings)} unmatched readings to process")

    sem = asyncio.Semaphore(CONCURRENCY)
    counters = {"inserted": 0, "matched": 0, "not_found": 0, "stop": False}

    # Process in batches of CONCURRENCY * 2
    batch_size = CONCURRENCY * 2
    for i in range(0, len(readings), batch_size):
        if budget_spent >= budget_limit or counters["stop"]:
            break
        batch = readings[i:i + batch_size]
        tasks = [_process_one_syllabus_reading(client, sem, r, counters) for r in batch]
        await asyncio.gather(*tasks)

    print(f"\n  Done: {counters['inserted']} new papers, {counters['matched']} linked, {counters['not_found']} not found, ${budget_spent:.3f}")
    return counters["inserted"]


# --- Main ---

async def async_main():
    global budget_limit, budget_spent, _budget_lock

    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Optimized Korczak graph seeding (Haiku)")
    parser.add_argument("--domain", choices=list(DOMAINS.keys()), help="Single domain to seed")
    parser.add_argument("--all-fields", action="store_true", help="Seed all 25 fields")
    parser.add_argument("--syllabus", action="store_true", help="Seed from syllabus readings")
    parser.add_argument("--journals", action="store_true", help="Seed from top high-impact journals")
    parser.add_argument("--journal", choices=list(TOP_JOURNALS.keys()), help="Single journal to seed")
    parser.add_argument("--sources", default="mit_ocw,open_syllabus", help="Syllabus sources (comma-separated)")
    parser.add_argument("--limit", type=int, default=500, help="Papers per domain")
    parser.add_argument("--budget", type=float, default=50.0, help="Max budget in USD")
    parser.add_argument("--concurrency", type=int, default=CONCURRENCY, help="Parallel API calls")
    args = parser.parse_args()

    budget_limit = args.budget
    _budget_lock = asyncio.Lock()

    _set_concurrency(args.concurrency)

    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        print("ERROR: Set SUPABASE_URL and SUPABASE_SERVICE_KEY in .env")
        sys.exit(1)
    if not ANTHROPIC_API_KEY:
        print("ERROR: Set ANTHROPIC_API_KEY in .env")
        sys.exit(1)

    init_supabase_headers()

    total = 0

    async with httpx.AsyncClient() as client:
        if args.syllabus:
            sources = [s.strip() for s in args.sources.split(",")]
            total = await seed_from_syllabi(client, sources)

        elif args.all_fields:
            print(f"Seeding ALL {len(DOMAINS)} fields, {args.limit} papers each")
            print(f"Estimated cost: ~${len(DOMAINS) * args.limit * 0.009:.0f}")
            print(f"Budget: ${budget_limit:.2f}")
            print(f"Concurrency: {CONCURRENCY} parallel API calls")

            for key in DOMAINS:
                if budget_spent >= budget_limit:
                    print(f"\n*** Budget exhausted — skipping remaining fields ***")
                    break
                total += await seed_domain(client, key, args.limit)

        elif args.domain:
            total = await seed_domain(client, args.domain, args.limit)

        elif args.journals:
            print(f"Seeding from {len(TOP_JOURNALS)} top journals, {args.limit} papers each")
            print(f"Budget: ${budget_limit:.2f}")
            print(f"Concurrency: {CONCURRENCY} parallel API calls")
            # Reuse seed_domain — it works with any domain dict that has source_id
            for key, journal in TOP_JOURNALS.items():
                if budget_spent >= budget_limit:
                    print(f"\n*** Budget exhausted ***")
                    break
                total += await seed_domain(client, key, args.limit)

        elif args.journal:
            total = await seed_domain(client, args.journal, args.limit)

        else:
            parser.error("Specify --domain, --all-fields, --syllabus, --journals, or --journal")

    print(f"\n{'='*60}")
    print(f"TOTAL: {total} papers seeded")
    print(f"COST:  ${budget_spent:.3f} / ${budget_limit:.2f}")
    print(f"RATE:  ${budget_spent/max(papers_analyzed,1):.4f}/paper")
    print(f"{'='*60}")


def main():
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
