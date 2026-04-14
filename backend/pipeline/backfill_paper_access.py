"""
Backfill access_url + access_status for existing papers (Feature 6.5, Stage B).

Fetches Unpaywall metadata for each paper that doesn't yet have access
fields resolved, and writes access_url / access_status / access_resolved_at.

This is lighter than fetch_full_text.py — it skips the HTML scraping step
and only uses Unpaywall's JSON metadata. Useful for quickly populating the
access fields across the whole corpus.

Usage:
  python -m backend.pipeline.backfill_paper_access --limit 500
  python -m backend.pipeline.backfill_paper_access --limit 50 --dry-run
"""

import argparse
from datetime import datetime, timezone
import os
import re
import sys
import time

import httpx
from dotenv import load_dotenv

from backend.core.access_resolver import resolve_access

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
OPENALEX_EMAIL = os.getenv("OPENALEX_EMAIL", "")

UNPAYWALL_BASE = "https://api.unpaywall.org/v2"

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


def fetch_unpaywall_metadata(doi: str) -> dict | None:
    """Fetch Unpaywall JSON metadata only (no HTML scraping)."""
    if not OPENALEX_EMAIL:
        return None
    clean_doi = re.sub(r"^https?://doi\.org/", "", doi)
    try:
        resp = httpx.get(
            f"{UNPAYWALL_BASE}/{clean_doi}",
            params={"email": OPENALEX_EMAIL},
            timeout=15,
        )
        if resp.status_code != 200:
            return None
        return resp.json()
    except Exception as e:
        print(f"    Unpaywall error: {e}")
        return None


def papers_needing_access(limit: int) -> list:
    """Papers with a DOI but no resolved access fields yet."""
    return supabase_get("papers", {
        "select": "id,doi,title",
        "doi": "not.is.null",
        "access_status": "is.null",
        "order": "cited_by_count.desc",
        "limit": str(limit),
    })


def run(limit: int, dry_run: bool = False) -> None:
    print(f"\n{'='*60}")
    print(f"ACCESS BACKFILL — limit={limit}, dry_run={dry_run}")
    if not OPENALEX_EMAIL:
        print("WARNING: OPENALEX_EMAIL not set — cannot call Unpaywall")
        return
    print(f"{'='*60}\n")

    papers = papers_needing_access(limit)
    print(f"Found {len(papers)} papers to resolve\n")

    stats = {"open": 0, "paywalled": 0, "hybrid": 0, "preprint": 0, "author_copy": 0, "unknown": 0, "errors": 0}

    for i, paper in enumerate(papers):
        title = (paper.get("title") or "?")[:60]
        doi = paper["doi"]
        print(f"[{i+1}/{len(papers)}] {title}...")

        unpaywall_data = fetch_unpaywall_metadata(doi)
        if unpaywall_data is None:
            # Fall through to resolver with DOI-only — will return 'unknown' unless DOI present
            pass

        access_url, access_status = resolve_access(unpaywall=unpaywall_data, doi=doi)
        stats[access_status] = stats.get(access_status, 0) + 1
        print(f"    -> {access_status} | {access_url}")

        if not dry_run:
            ok = supabase_patch(
                "papers",
                {"id": f"eq.{paper['id']}"},
                {
                    "access_url": access_url,
                    "access_status": access_status,
                    "access_resolved_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            if not ok:
                stats["errors"] += 1

        # Unpaywall allows 100k requests/day and does not require per-request
        # rate limiting, but a small delay keeps us courteous.
        time.sleep(0.2)

    print(f"\n{'='*60}")
    print("ACCESS STATUS DISTRIBUTION:")
    for k in ("open", "hybrid", "preprint", "author_copy", "paywalled", "unknown"):
        print(f"  {k:12s}  {stats.get(k, 0)}")
    if stats["errors"]:
        print(f"  errors       {stats['errors']}")
    print(f"{'='*60}")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Backfill paper access_url + access_status from Unpaywall")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        print("ERROR: Set SUPABASE_URL and SUPABASE_SERVICE_KEY in .env")
        sys.exit(1)

    run(args.limit, args.dry_run)


if __name__ == "__main__":
    main()
