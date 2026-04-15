"""Mark the Nature Top 100 most-cited papers (2014 Van Noorden list).

The Nature list is heavy on *method* papers (Lowry, Laemmli, Bradford,
Sanger sequencing, BLAST, Kaplan-Meier, Cox regression, CLUSTAL W, etc.)
— the infrastructure of modern science. Tagging them canonical pushes
these foundational tools to the top of the knowledge graph.

Many of these overlap with the Google Scholar Top 100; this script is
idempotent — it just upgrades existing rows with canonical_field +
canonical_rank.

Usage:
  python -m backend.pipeline.mark_nature_top100
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Optional

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


async def find_paper(client, title: str) -> Optional[dict]:
    # Try fuzzy title match
    short = title[:60].replace("'", "").replace(":", "").replace("&", "")
    results = await supabase_get(client, "papers", {
        "title": f"ilike.*{short[:40]}*", "select": "id,title", "limit": "3",
    })
    for r in results:
        if title.lower()[:30] in (r["title"] or "").lower():
            return r
    return results[0] if results else None


async def fetch_openalex(client, title: str) -> Optional[dict]:
    try:
        r = await client.get(f"{OPENALEX_BASE}/works", params={
            "search": title,
            "per_page": 3,
            "select": "id,title,authorships,publication_year,cited_by_count,doi,primary_location",
        }, timeout=15)
        if r.status_code == 200:
            results = r.json().get("results", [])
            return results[0] if results else None
    except Exception:
        pass
    return None


async def process(client, work: dict, stats: dict):
    title = work["title"]
    rank = work["rank"]

    existing = await find_paper(client, title)
    if existing:
        await supabase_patch(client, "papers", {"id": f"eq.{existing['id']}"}, {
            "canonical": True,
            "canonical_field": "canonical-nature-top100",
            "canonical_rank": rank,
            "canonical_reason": f"Nature Top 100 most-cited papers (#{rank}, {work.get('author','')}, {work.get('year','')})",
        })
        # Upsert canonical_works
        cw = await supabase_get(client, "canonical_works", {
            "field": "eq.canonical-nature-top100", "title": f"eq.{title}", "select": "id",
        })
        if cw:
            await supabase_patch(client, "canonical_works", {"id": f"eq.{cw[0]['id']}"}, {
                "paper_id": existing["id"],
            })
        else:
            await supabase_post(client, "canonical_works", {
                "field": "canonical-nature-top100", "title": title, "author": work.get("author"),
                "year": work.get("year"), "rank": rank, "paper_id": existing["id"],
                "why": f"Nature Top 100 foundational method/research paper (#{rank})",
            })
        stats["db_marked"] += 1
        print(f"  ✓ #{rank:3} [DB] {title[:65]}")
        return

    # Not in DB — fetch from OpenAlex as metadata stub
    raw = await fetch_openalex(client, title)
    if not raw:
        stats["not_found"] += 1
        print(f"  ✗ #{rank:3} [NOT FOUND] {title[:65]}")
        return

    oa_id = raw["id"].split("/")[-1]
    existing_by_oa = await supabase_get(client, "papers", {
        "openalex_id": f"eq.{oa_id}", "select": "id",
    })
    if existing_by_oa:
        paper_id = existing_by_oa[0]["id"]
        await supabase_patch(client, "papers", {"id": f"eq.{paper_id}"}, {
            "canonical": True,
            "canonical_field": "canonical-nature-top100",
            "canonical_rank": rank,
            "canonical_reason": f"Nature Top 100 foundational method/research paper (#{rank})",
        })
        stats["db_marked"] += 1
        print(f"  ✓ #{rank:3} [DB by OA] {title[:65]}")
        return

    authorships = raw.get("authorships", [])
    authors_json = json.dumps([
        {"name": a.get("author", {}).get("display_name", "")} for a in authorships[:10]
    ])
    paper_row = {
        "openalex_id": oa_id,
        "doi": raw.get("doi"),
        "title": raw.get("title", title),
        "authors": authors_json,
        "publication_year": raw.get("publication_year") or work.get("year"),
        "source_journal": ((raw.get("primary_location") or {}).get("source") or {}).get("display_name"),
        "cited_by_count": raw.get("cited_by_count", 0),
        "canonical": True,
        "canonical_field": "canonical-nature-top100",
        "canonical_rank": rank,
        "canonical_reason": f"Nature Top 100 foundational method/research paper (#{rank})",
        "is_stub": True,
    }
    res = await supabase_post(client, "papers", paper_row)
    if res:
        paper_id = res[0]["id"]
        await supabase_post(client, "canonical_works", {
            "field": "canonical-nature-top100", "title": title, "author": work.get("author"),
            "year": work.get("year"), "rank": rank, "paper_id": paper_id,
            "why": f"Nature Top 100 foundational method/research paper (#{rank})",
        })
        stats["inserted"] += 1
        print(f"  + #{rank:3} [NEW stub] {title[:65]}")
    else:
        stats["not_found"] += 1


async def async_main():
    sys.stdout.reconfigure(encoding="utf-8")
    with open("data/nature_top_100_methods.json", encoding="utf-8") as f:
        data = json.load(f)

    print(f"\n{'='*60}")
    print(f"NATURE TOP 100 CANONICAL MARKING")
    print(f"Works to process: {len(data['works'])}")
    print(f"{'='*60}\n")

    stats = {"db_marked": 0, "inserted": 0, "not_found": 0}
    async with httpx.AsyncClient() as client:
        for work in data["works"]:
            try:
                await process(client, work, stats)
            except Exception as e:
                print(f"  ERROR #{work.get('rank')}: {e}")

    print(f"\n{'='*60}")
    print(f"  DB-marked: {stats['db_marked']}")
    print(f"  New stubs: {stats['inserted']}")
    print(f"  Not found: {stats['not_found']}")
    print(f"{'='*60}")


def main():
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
