"""
Citation expansion pipeline.

For each important paper in the DB (canonical + top-cited), fetch its most-cited
references from OpenAlex and seed them into the graph. This builds dense
citation networks around foundational works.

Usage:
  python -m backend.pipeline.seed_citations --budget 20
  python -m backend.pipeline.seed_citations --budget 20 --from-canonical
  python -m backend.pipeline.seed_citations --budget 20 --source-papers 100
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
OPENALEX_BASE = "https://api.openalex.org"
ANTHROPIC_API = "https://api.anthropic.com/v1/messages"

HAIKU_INPUT_COST = 0.80 / 1_000_000
HAIKU_OUTPUT_COST = 4.0 / 1_000_000

CONCURRENCY = 10

budget_spent = 0.0
budget_limit = 20.0
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

from backend.prompts.paper_analysis import ANALYSIS_PROMPT
from backend.pipeline.claim_builder import build_claim_row


# --- Supabase helpers ---

async def supabase_get(client, table, params):
    r = await client.get(
        f"{SUPABASE_URL}/rest/v1/{table}",
        params=params, headers={**HEADERS_SUPABASE, "Prefer": ""}, timeout=15,
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


def normalize_name(name):
    return re.sub(r"[^a-z0-9\s]", "", name.lower()).strip()


def reconstruct_abstract(inv):
    if not inv:
        return ""
    positions = []
    for word, poss in inv.items():
        for p in poss:
            positions.append((p, word))
    positions.sort()
    return " ".join(w for _, w in positions)


async def get_or_create_concept(client, c):
    norm = normalize_name(c["name"])
    existing = await supabase_get(client, "concepts", {
        "normalized_name": f"eq.{norm}", "select": "id",
    })
    if existing:
        return existing[0]["id"]
    row = {
        "name": c["name"],
        "normalized_name": norm,
        "type": c.get("type", "phenomenon"),
        "definition": c.get("definition"),
        "confidence": 0.6,
    }
    result = await supabase_post(client, "concepts", row)
    return result[0]["id"] if result else None


# --- OpenAlex ---

async def fetch_references(client, openalex_id, limit=20):
    """Get top-cited references of a paper from OpenAlex."""
    try:
        r = await client.get(f"{OPENALEX_BASE}/works/{openalex_id}", params={
            "select": "referenced_works",
        }, timeout=15)
        if r.status_code != 200:
            return []
        refs = r.json().get("referenced_works", [])[:50]
        if not refs:
            return []
        # Fetch metadata for these refs
        ref_ids = [r.split("/")[-1] for r in refs]
        id_filter = "|".join(ref_ids)
        r2 = await client.get(f"{OPENALEX_BASE}/works", params={
            "filter": f"openalex:{id_filter},has_abstract:true",
            "sort": "cited_by_count:desc",
            "per_page": str(limit),
            "select": "id,title,authorships,publication_year,abstract_inverted_index,cited_by_count,doi,primary_location",
        }, timeout=15)
        if r2.status_code == 200:
            return r2.json().get("results", [])
    except Exception:
        pass
    return []


# --- Claude analysis ---

async def analyze_with_haiku(client, title, authors, year, abstract):
    global budget_spent, papers_analyzed

    if not abstract or len(abstract) < 50:
        return None

    async with _budget_lock:
        if budget_spent >= budget_limit:
            return "STOP"

    prompt = ANALYSIS_PROMPT.format(title=title, authors=authors, year=year, abstract=abstract)
    body = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 2000,
        "temperature": 0.2,
        "messages": [{"role": "user", "content": prompt}],
    }
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "content-type": "application/json",
        "anthropic-version": "2023-06-01",
    }

    for attempt in range(2):
        try:
            r = await client.post(ANTHROPIC_API, json=body, headers=headers, timeout=60)
            if r.status_code == 429:
                await asyncio.sleep(5)
                continue
            if r.status_code in (402, 529):
                return "STOP"
            r.raise_for_status()
            data = r.json()
            text = data["content"][0]["text"]
            usage = data.get("usage", {})
            cost = usage.get("input_tokens", 0) * HAIKU_INPUT_COST + usage.get("output_tokens", 0) * HAIKU_OUTPUT_COST
            async with _budget_lock:
                budget_spent += cost
                papers_analyzed += 1
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


async def insert_paper(client, raw, analysis, source_paper_id=None):
    """Insert a new paper with its analysis + link as reference from source."""
    try:
        oa_id = raw["id"].split("/")[-1]

        # Skip if already in DB
        existing = await supabase_get(client, "papers", {
            "openalex_id": f"eq.{oa_id}", "select": "id",
        })
        if existing:
            paper_id = existing[0]["id"]
        else:
            pt = analysis.get("paper_type") or {}
            authorships = raw.get("authorships", [])
            authors_json = json.dumps([
                {"name": a.get("author", {}).get("display_name", "")}
                for a in authorships[:10]
            ])
            paper_row = {
                "openalex_id": oa_id,
                "doi": raw.get("doi"),
                "title": raw.get("title", ""),
                "authors": authors_json,
                "publication_year": raw.get("publication_year"),
                "abstract": reconstruct_abstract(raw.get("abstract_inverted_index")),
                "paper_type": pt.get("type"),
                "subfield": pt.get("subfield"),
                "source_journal": ((raw.get("primary_location") or {}).get("source") or {}).get("display_name"),
                "cited_by_count": raw.get("cited_by_count", 0),
                "analysis": json.dumps(analysis),
                "analysis_model": "claude-haiku-4-5-20251001",
                "analyzed_at": datetime.now(tz=timezone.utc).isoformat(),
            }
            result = await supabase_post(client, "papers", paper_row)
            if not result:
                return None
            paper_id = result[0]["id"]

            # Insert concepts & claims (simplified)
            concept_ids = {}
            for c in analysis.get("concepts", []):
                cid = await get_or_create_concept(client, c)
                if cid:
                    concept_ids[c["name"]] = cid
                    await supabase_post(client, "paper_concepts", {
                        "paper_id": paper_id, "concept_id": cid,
                        "novelty_in_paper": c.get("novelty_at_time", "low"),
                        "well_established": c.get("well_established", True),
                    })
            for cl in analysis.get("claims", []):
                claim_text = cl.get("claim") or cl.get("claim_text")
                if claim_text:
                    await supabase_post(
                        client,
                        "claims",
                        build_claim_row(paper_id, cl, claim_text_override=claim_text),
                    )

        # Link as reference from source
        if source_paper_id and paper_id != source_paper_id:
            await supabase_post(client, "relationships", {
                "source_type": "paper", "source_id": source_paper_id,
                "target_type": "paper", "target_id": paper_id,
                "relationship_type": "CITES",
                "confidence": 1.0,
                "explanation": "OpenAlex referenced_works",
                "paper_id": source_paper_id,
            })

        return paper_id
    except Exception as e:
        print(f"    Insert error: {e}")
        return None


# --- Main pipeline ---

async def expand_citations(client, source_papers, refs_per_paper):
    """For each source paper, fetch and analyze its top references."""
    print(f"\n{'='*60}")
    print(f"CITATION EXPANSION")
    print(f"Source papers: {len(source_papers)} | Refs each: {refs_per_paper}")
    print(f"Budget: ${budget_limit:.2f}")
    print(f"{'='*60}\n")

    sem = asyncio.Semaphore(CONCURRENCY)
    stats = {"new_papers": 0, "already_exist": 0, "no_refs": 0, "errors": 0, "citations_linked": 0}

    async def process_reference(source_paper, raw):
        if budget_spent >= budget_limit:
            return
        async with sem:
            if budget_spent >= budget_limit:
                return
            try:
                oa_id = raw["id"].split("/")[-1]
                existing = await supabase_get(client, "papers", {
                    "openalex_id": f"eq.{oa_id}", "select": "id",
                })
                if existing:
                    # Already in DB — just link
                    await supabase_post(client, "relationships", {
                        "source_type": "paper", "source_id": source_paper["id"],
                        "target_type": "paper", "target_id": existing[0]["id"],
                        "relationship_type": "CITES",
                        "confidence": 1.0,
                        "explanation": "OpenAlex referenced_works",
                        "paper_id": source_paper["id"],
                    })
                    stats["already_exist"] += 1
                    stats["citations_linked"] += 1
                    return

                # New paper — analyze
                abstract = reconstruct_abstract(raw.get("abstract_inverted_index"))
                if not abstract or len(abstract) < 50:
                    return
                authors_list = raw.get("authorships", [])
                authors_str = ", ".join(
                    a.get("author", {}).get("display_name", "") for a in authors_list[:5]
                )
                title = raw.get("title", "?")
                year = raw.get("publication_year", 0)

                analysis = await analyze_with_haiku(client, title, authors_str, year, abstract)
                if analysis == "STOP":
                    return
                if analysis and not isinstance(analysis, str):
                    pid = await insert_paper(client, raw, analysis, source_paper["id"])
                    if pid:
                        stats["new_papers"] += 1
                        stats["citations_linked"] += 1
                        if stats["new_papers"] % 10 == 0:
                            print(f"  [{stats['new_papers']} new] {title[:55]}... ${budget_spent:.3f}")
                    else:
                        stats["errors"] += 1
            except Exception as e:
                stats["errors"] += 1

    # Process each source paper
    for i, sp in enumerate(source_papers):
        if budget_spent >= budget_limit:
            print(f"\n*** BUDGET LIMIT ***")
            break
        if not sp.get("openalex_id"):
            continue

        refs = await fetch_references(client, sp["openalex_id"], refs_per_paper)
        if not refs:
            stats["no_refs"] += 1
            continue

        if i % 10 == 0 and i > 0:
            print(f"\n[Source {i}/{len(source_papers)}] {sp['title'][:50]}... ({len(refs)} refs)")

        # Process references concurrently
        tasks = [process_reference(sp, r) for r in refs]
        await asyncio.gather(*tasks)

    print(f"\n{'='*60}")
    print(f"CITATION EXPANSION RESULTS:")
    print(f"  New papers:        {stats['new_papers']}")
    print(f"  Already in DB:     {stats['already_exist']}")
    print(f"  Citations linked:  {stats['citations_linked']}")
    print(f"  No refs available: {stats['no_refs']}")
    print(f"  Errors:            {stats['errors']}")
    print(f"  Cost:              ${budget_spent:.3f} / ${budget_limit:.2f}")
    print(f"{'='*60}")


async def async_main():
    global budget_limit, _budget_lock

    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Citation expansion: seed refs from existing papers")
    parser.add_argument("--budget", type=float, default=20.0)
    parser.add_argument("--source-papers", type=int, default=200, help="Number of source papers to expand from")
    parser.add_argument("--refs-per-paper", type=int, default=15, help="Max references to pull per source")
    parser.add_argument("--from-canonical", action="store_true", help="Only expand from canonical works")
    args = parser.parse_args()

    budget_limit = args.budget
    _budget_lock = asyncio.Lock()
    init_supabase_headers()

    async with httpx.AsyncClient() as client:
        # Get source papers
        if args.from_canonical:
            source_papers = await supabase_get(client, "papers", {
                "canonical": "eq.true",
                "openalex_id": "not.is.null",
                "select": "id,title,openalex_id",
                "order": "canonical_rank.asc",
                "limit": str(args.source_papers),
            })
        else:
            source_papers = await supabase_get(client, "papers", {
                "openalex_id": "not.is.null",
                "is_stub": "eq.false",
                "select": "id,title,openalex_id",
                "order": "cited_by_count.desc",
                "limit": str(args.source_papers),
            })

        print(f"Got {len(source_papers)} source papers")
        await expand_citations(client, source_papers, args.refs_per_paper)


def main():
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
