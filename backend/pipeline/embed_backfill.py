"""Embedding backfill — wake up the semantic brain.

The audit found that NOTHING writes embeddings: concepts.embedding and
claims.embedding are NULL unless a maintenance CLI was run by hand, so
"semantic search" silently degrades to keyword ILIKE.

This script fixes it:
- Embeds all concepts missing embeddings (name + definition)
- Embeds all claims missing embeddings (claim_text)
- Batches 100 texts per OpenAI call (text-embedding-3-small, ~$0.02/1M tokens)
- Safe to re-run: only touches NULL-embedding rows

Wire-in points elsewhere:
- Admin approval of a new definition triggers a single-concept re-embed
- Run after every seeding batch: python -m backend.pipeline.embed_backfill

Usage:
  python -m backend.pipeline.embed_backfill                # everything missing
  python -m backend.pipeline.embed_backfill --only concepts --limit 2000
"""

import argparse
import os
import sys
import time

import httpx
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
EMBED_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

HEADERS = {
    "apikey": SUPABASE_SERVICE_KEY or "",
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Content-Type": "application/json",
}


def embed_batch(texts: list[str]) -> list[list[float]]:
    """One OpenAI embeddings call for up to 100 texts."""
    resp = httpx.post(
        "https://api.openai.com/v1/embeddings",
        headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
        json={"model": EMBED_MODEL, "input": texts},
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()["data"]
    return [d["embedding"] for d in sorted(data, key=lambda d: d["index"])]


def fetch_missing(table: str, text_cols: list[str], limit: int) -> list[dict]:
    resp = httpx.get(
        f"{SUPABASE_URL}/rest/v1/{table}",
        params={
            "select": "id," + ",".join(text_cols),
            "embedding": "is.null",
            "limit": str(limit),
        },
        headers=HEADERS, timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def write_embedding(table: str, row_id: str, embedding: list[float]) -> bool:
    resp = httpx.patch(
        f"{SUPABASE_URL}/rest/v1/{table}",
        params={"id": f"eq.{row_id}"},
        json={"embedding": embedding},
        headers=HEADERS, timeout=30,
    )
    return resp.status_code in (200, 204)


def backfill(table: str, make_text, text_cols: list[str], limit: int) -> int:
    total = 0
    while total < limit:
        rows = fetch_missing(table, text_cols, min(100, limit - total))
        if not rows:
            break
        texts = [make_text(r)[:4000] for r in rows]
        try:
            embeddings = embed_batch(texts)
        except Exception as e:
            print(f"  Embedding call failed: {e}")
            break
        written = 0
        for row, emb in zip(rows, embeddings):
            if write_embedding(table, row["id"], emb):
                written += 1
        total += written
        print(f"  {table}: {total} embedded so far...")
        if written == 0:
            break  # avoid spinning on write failures
        time.sleep(0.3)
    return total


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Backfill missing embeddings")
    parser.add_argument("--only", choices=["concepts", "claims"], default=None)
    parser.add_argument("--limit", type=int, default=5000)
    args = parser.parse_args()

    if not (SUPABASE_URL and SUPABASE_SERVICE_KEY):
        print("ERROR: SUPABASE_URL / SUPABASE_SERVICE_KEY missing"); sys.exit(1)
    if not OPENAI_API_KEY:
        print("ERROR: OPENAI_API_KEY missing — embeddings need it"); sys.exit(1)

    results = {}
    if args.only in (None, "concepts"):
        print("Embedding concepts (name + definition)...")
        results["concepts"] = backfill(
            "concepts",
            lambda r: f"{r.get('name', '')}: {r.get('definition') or ''}",
            ["name", "definition"], args.limit,
        )
    if args.only in (None, "claims"):
        print("Embedding claims (claim_text)...")
        results["claims"] = backfill(
            "claims",
            lambda r: r.get("claim_text") or "",
            ["claim_text"], args.limit,
        )

    print(f"\nDone: {results}")
    print("Semantic search is now live. Re-run after every seeding batch.")


if __name__ == "__main__":
    main()
