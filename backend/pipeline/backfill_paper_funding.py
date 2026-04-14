"""
Backfill `papers.funding` from OpenAlex `grants` for existing papers
(Feature 6.5, Stage B).

Our `papers.funding` JSONB has been `[]` for the entire existing corpus
because the original seeding pipelines didn't request `grants` from
OpenAlex. This script re-fetches each paper that has `openalex_id` and
`funding = []` and writes the grants data.

The same pass also updates `papers.authors[]` with country + ROR ID for
each authorship (again, data that was dropped during the original seed).

Usage:
  python -m backend.pipeline.backfill_paper_funding --limit 500
  python -m backend.pipeline.backfill_paper_funding --limit 50 --dry-run
"""

import argparse
import asyncio
import os
import sys

import httpx
from dotenv import load_dotenv

from backend.integrations.openalex_client import fetch_work_by_id

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

HEADERS_SUPABASE = {
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}


def supabase_get(table: str, params: dict) -> list:
    resp = httpx.get(
        f"{SUPABASE_URL}/rest/v1/{table}",
        params=params,
        headers={**HEADERS_SUPABASE, "Prefer": ""},
        timeout=15,
    )
    if resp.status_code == 200:
        return resp.json()
    print(f"  Supabase GET error: {resp.status_code} {resp.text[:200]}")
    return []


def supabase_patch(table: str, match_params: dict, data: dict) -> bool:
    resp = httpx.patch(
        f"{SUPABASE_URL}/rest/v1/{table}",
        params=match_params,
        json=data,
        headers=HEADERS_SUPABASE,
        timeout=15,
    )
    if resp.status_code in (200, 204):
        return True
    print(f"  Supabase PATCH error: {resp.status_code} {resp.text[:200]}")
    return False


def papers_missing_funding(limit: int) -> list[dict]:
    """Papers that have an OpenAlex ID but no funding data yet."""
    return supabase_get("papers", {
        "select": "id,openalex_id,title,funding,authors",
        "openalex_id": "not.is.null",
        "funding": "eq.[]",
        "order": "cited_by_count.desc",
        "limit": str(limit),
    })


def _merge_author_enrichment(db_authors: list[dict], fresh_authors: list[dict]) -> list[dict]:
    """Merge country/ROR/institutions from fresh_authors into db_authors.

    Matches by openalex_id (preferred), falling back to name. Only overwrites
    fields that are missing in the existing record to avoid clobbering manual
    edits or prior enrichment.
    """
    fresh_by_openalex = {a.get("openalex_id"): a for a in fresh_authors if a.get("openalex_id")}
    fresh_by_name = {a.get("name"): a for a in fresh_authors if a.get("name")}

    enriched = []
    for a in db_authors:
        match = (
            fresh_by_openalex.get(a.get("openalex_id"))
            or fresh_by_name.get(a.get("name"))
        )
        if match:
            for key in ("institution_ror_id", "country", "institutions"):
                if not a.get(key) and match.get(key):
                    a[key] = match[key]
            if not a.get("institution") and match.get("institution"):
                a["institution"] = match["institution"]
        enriched.append(a)
    return enriched


async def run(limit: int, dry_run: bool = False) -> None:
    print(f"\n{'='*60}")
    print(f"FUNDING + COUNTRY BACKFILL — limit={limit}, dry_run={dry_run}")
    print(f"{'='*60}\n")

    papers = papers_missing_funding(limit)
    print(f"Found {len(papers)} papers missing funding\n")

    stats = {"funded": 0, "no_grants": 0, "country_added": 0, "errors": 0}

    for i, paper in enumerate(papers):
        openalex_id = paper["openalex_id"]
        title = (paper.get("title") or "?")[:60]
        print(f"[{i+1}/{len(papers)}] {title}...")

        fresh = await fetch_work_by_id(openalex_id)
        if fresh is None:
            print("    -> OpenAlex fetch failed")
            stats["errors"] += 1
            continue

        patch: dict = {}

        funding = fresh.get("funding") or []
        if funding:
            patch["funding"] = funding
            stats["funded"] += 1
        else:
            stats["no_grants"] += 1

        fresh_authors = fresh.get("authors") or []
        if fresh_authors:
            merged = _merge_author_enrichment(paper.get("authors") or [], fresh_authors)
            # Only write if something actually changed
            if merged != (paper.get("authors") or []):
                patch["authors"] = merged
                if any(a.get("country") for a in merged):
                    stats["country_added"] += 1

        if not patch:
            print("    -> nothing new")
            continue

        print(f"    -> funding={len(funding)} | country_enriched={'country' in (merged[0] if fresh_authors else {})}")
        if not dry_run:
            if not supabase_patch("papers", {"id": f"eq.{paper['id']}"}, patch):
                stats["errors"] += 1

        await asyncio.sleep(0.15)  # OpenAlex is generous but stay polite

    print(f"\n{'='*60}")
    print("RESULTS:")
    print(f"  Papers with funding added:  {stats['funded']}")
    print(f"  Papers with no grants:      {stats['no_grants']}")
    print(f"  Papers with country added:  {stats['country_added']}")
    print(f"  Errors:                     {stats['errors']}")
    print(f"{'='*60}")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Backfill papers.funding + author countries from OpenAlex")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        print("ERROR: Set SUPABASE_URL and SUPABASE_SERVICE_KEY in .env")
        sys.exit(1)

    asyncio.run(run(args.limit, args.dry_run))


if __name__ == "__main__":
    main()
