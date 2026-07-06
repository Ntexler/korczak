"""Backfill the papers.field column (migration 027).

One-time: computes normalize_field(subfield) for every paper and persists it.
After this + the migration, every field-scoped query uses the index instead
of scanning the whole table per request.

Usage:
  python -m backend.pipeline.backfill_fields
"""

import os
import sys

import httpx
from dotenv import load_dotenv

load_dotenv()

from backend.core.fields import normalize_field

SUPABASE_URL = os.getenv("SUPABASE_URL")
HEADERS = {
    "apikey": os.getenv("SUPABASE_SERVICE_KEY") or "",
    "Authorization": f"Bearer {os.getenv('SUPABASE_SERVICE_KEY')}",
    "Content-Type": "application/json",
}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if not SUPABASE_URL:
        print("ERROR: SUPABASE_URL / SUPABASE_SERVICE_KEY missing"); sys.exit(1)

    updated, skipped, offset = 0, 0, 0
    while True:
        resp = httpx.get(
            f"{SUPABASE_URL}/rest/v1/papers",
            params={"select": "id,subfield,field", "field": "is.null",
                    "limit": "500", "offset": str(offset)},
            headers=HEADERS, timeout=30,
        )
        resp.raise_for_status()
        rows = resp.json()
        if not rows:
            break

        for p in rows:
            field = normalize_field(p.get("subfield") or "")
            if not field:
                skipped += 1
                continue
            r = httpx.patch(
                f"{SUPABASE_URL}/rest/v1/papers",
                params={"id": f"eq.{p['id']}"},
                json={"field": field},
                headers=HEADERS, timeout=15,
            )
            if r.status_code in (200, 204):
                updated += 1

        print(f"  {updated} updated, {skipped} unmapped so far...")
        # unmapped rows stay field=null, so paginate past them
        offset = skipped

    print(f"\nDone: {updated} papers assigned a field, {skipped} had unmappable subfields.")


if __name__ == "__main__":
    main()
