"""
Mark canonical papers in the graph.

Reads data/full_text_priority.json and:
1. Creates canonical_works entries for each
2. Tries to find matching paper in DB — if found, marks it canonical + links
3. If not found, tries OpenAlex — if found, seeds it with canonical flag
4. If still not found, creates a stub paper entry (metadata only, no analysis) so
   the system "knows about" the work and can reference it

Usage:
  python -m backend.pipeline.mark_canonical
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
OPENALEX_BASE = "https://api.openalex.org"

HEADERS_SUPABASE = {
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}


async def supabase_get(client, table, params):
    r = await client.get(
        f"{SUPABASE_URL}/rest/v1/{table}",
        params=params,
        headers={**HEADERS_SUPABASE, "Prefer": ""},
        timeout=15,
    )
    return r.json() if r.status_code == 200 else []


async def supabase_post(client, table, data):
    r = await client.post(
        f"{SUPABASE_URL}/rest/v1/{table}",
        json=data, headers=HEADERS_SUPABASE, timeout=15,
    )
    if r.status_code in (200, 201):
        return r.json()
    if r.status_code == 409:
        return None
    print(f"    POST error ({table}): {r.status_code} {r.text[:150]}")
    return None


async def supabase_patch(client, table, params, data):
    r = await client.patch(
        f"{SUPABASE_URL}/rest/v1/{table}",
        params=params, json=data, headers=HEADERS_SUPABASE, timeout=15,
    )
    return r.status_code in (200, 204)


async def search_openalex(client, title, author=""):
    """Find a paper in OpenAlex by title + author."""
    search = f"{title} {author}".strip()
    try:
        r = await client.get(f"{OPENALEX_BASE}/works", params={
            "search": search,
            "per_page": 3,
            "select": "id,title,authorships,publication_year,abstract_inverted_index,cited_by_count,doi,primary_location",
        }, timeout=15)
        if r.status_code == 200:
            results = r.json().get("results", [])
            # Take first result that has a reasonable title match
            for w in results:
                w_title = (w.get("title") or "").lower()
                if title.lower()[:20] in w_title:
                    return w
            if results:
                return results[0]
    except Exception:
        pass
    return None


def reconstruct_abstract(inv):
    if not inv:
        return ""
    positions = []
    for word, poss in inv.items():
        for p in poss:
            positions.append((p, word))
    positions.sort()
    return " ".join(w for _, w in positions)


async def process_canonical_work(client, work, field, rank):
    """For each canonical work, find/create the paper and mark as canonical."""
    title = work["title"]
    author = work.get("author", "")
    year = work.get("year")
    why = work.get("why", "")

    # 1. Check if we have a canonical_works entry already
    existing_cw = await supabase_get(client, "canonical_works", {
        "field": f"eq.{field}",
        "title": f"eq.{title}",
        "select": "id,paper_id",
    })
    if existing_cw and existing_cw[0].get("paper_id"):
        return "already_linked"

    # 2. Insert/get canonical_works entry
    if not existing_cw:
        cw_result = await supabase_post(client, "canonical_works", {
            "field": field,
            "title": title,
            "author": author,
            "year": year,
            "why": why,
            "rank": rank,
        })
        cw_id = cw_result[0]["id"] if cw_result else None
    else:
        cw_id = existing_cw[0]["id"]

    # 3. Try to find paper in DB
    # Search by title (fuzzy)
    title_short = title[:40].replace("'", "").replace(":", "")
    matches = await supabase_get(client, "papers", {
        "title": f"ilike.*{title_short}*",
        "select": "id,title,openalex_id",
        "limit": "5",
    })

    paper_id = None
    for m in matches:
        if m["title"].lower()[:30] == title.lower()[:30]:
            paper_id = m["id"]
            break

    # 4. If not in DB, try OpenAlex
    if not paper_id:
        raw = await search_openalex(client, title, author)
        if raw:
            oa_id = raw["id"].split("/")[-1]
            # Check if this OpenAlex ID is already in DB
            existing = await supabase_get(client, "papers", {
                "openalex_id": f"eq.{oa_id}", "select": "id",
            })
            if existing:
                paper_id = existing[0]["id"]
            else:
                # Create minimal entry (stub with some real data from OpenAlex)
                authorships = raw.get("authorships", [])
                authors_json = json.dumps([
                    {"name": a.get("author", {}).get("display_name", "")}
                    for a in authorships[:10]
                ])
                paper_row = {
                    "openalex_id": oa_id,
                    "doi": raw.get("doi"),
                    "title": raw.get("title", title),
                    "authors": authors_json,
                    "publication_year": raw.get("publication_year") or year,
                    "abstract": reconstruct_abstract(raw.get("abstract_inverted_index")),
                    "source_journal": ((raw.get("primary_location") or {}).get("source") or {}).get("display_name"),
                    "cited_by_count": raw.get("cited_by_count", 0),
                    "canonical": True,
                    "canonical_field": field,
                    "canonical_rank": rank,
                    "canonical_reason": why,
                    "is_stub": True,  # no analysis yet
                }
                pr = await supabase_post(client, "papers", paper_row)
                if pr:
                    paper_id = pr[0]["id"]
                    print(f"    -> Created OpenAlex-enriched stub for '{title[:50]}'")

    # 5. Still not found → pure stub with just the metadata we have
    if not paper_id:
        paper_row = {
            "title": title,
            "authors": json.dumps([{"name": author}] if author else []),
            "publication_year": year,
            "cited_by_count": 0,
            "canonical": True,
            "canonical_field": field,
            "canonical_rank": rank,
            "canonical_reason": why,
            "is_stub": True,
        }
        pr = await supabase_post(client, "papers", paper_row)
        if pr:
            paper_id = pr[0]["id"]
            print(f"    -> Created PURE stub for '{title[:50]}' — needs manual enrichment")

    # 6. Mark existing paper as canonical
    if paper_id:
        await supabase_patch(client, "papers", {"id": f"eq.{paper_id}"}, {
            "canonical": True,
            "canonical_field": field,
            "canonical_rank": rank,
            "canonical_reason": why,
        })
        # Link to canonical_works
        if cw_id:
            await supabase_patch(client, "canonical_works", {"id": f"eq.{cw_id}"}, {
                "paper_id": paper_id,
            })
        return "marked"

    return "failed"


async def async_main():
    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Mark canonical works in the knowledge graph")
    parser.add_argument("--priority-file", default="data/full_text_priority.json")
    args = parser.parse_args()

    with open(args.priority_file) as f:
        data = json.load(f)

    stats = {"marked": 0, "stubs_created": 0, "already_linked": 0, "failed": 0}

    print(f"\n{'='*60}")
    print(f"MARKING CANONICAL WORKS")
    print(f"{'='*60}")

    async with httpx.AsyncClient() as client:
        for field_group in data.get("papers", []):
            field = field_group["field"]
            works = field_group.get("works", [])
            print(f"\n--- {field} ({len(works)} works) ---")
            for rank, work in enumerate(works, 1):
                try:
                    result = await process_canonical_work(client, work, field, rank)
                    if result == "marked":
                        stats["marked"] += 1
                        print(f"  [{rank}] ✓ {work['title'][:60]}")
                    elif result == "already_linked":
                        stats["already_linked"] += 1
                    else:
                        stats["failed"] += 1
                        print(f"  [{rank}] ✗ {work['title'][:60]}")
                except Exception as e:
                    print(f"  [{rank}] ERROR: {e}")
                    stats["failed"] += 1

    print(f"\n{'='*60}")
    print(f"RESULTS:")
    print(f"  Marked:          {stats['marked']}")
    print(f"  Already linked:  {stats['already_linked']}")
    print(f"  Failed:          {stats['failed']}")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(async_main())
