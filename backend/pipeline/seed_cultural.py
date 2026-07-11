"""Cultural memory seeding — the history of ideas and primary texts.

"Not only science." This pulls the cultural record into the graph as
first-class works: philosophy classics, historical documents, primary
texts from the Internet Archive. Free, no LLM required for the base.

Each work:
- source='internet_archive', work_kind='book'/'primary_text'
- has_fulltext + external_url so it opens in a reading room
- concepts extracted from its subject tags (free) — deeper analysis
  happens lazily when a user actually opens it

Curated seed topics span the history of ideas across cultures — the
translation movement, classical texts, foundational works — not a random
crawl. Admin can add topics.

Usage:
  python -m backend.pipeline.seed_cultural --topic "history of ideas" --field History --limit 20
  python -m backend.pipeline.seed_cultural --curated
"""

import argparse
import asyncio
import json
import os
import sys

from dotenv import load_dotenv

load_dotenv()

import backend.pipeline.seed_optimized as seed_opt
from backend.pipeline.seed_optimized import init_supabase_headers, supabase_post, supabase_get, normalize_name

SUPABASE_URL = os.getenv("SUPABASE_URL")

# Curated history-of-ideas seed set — the cultural record, across traditions
CURATED = [
    {"topic": "Plato Republic dialogues", "field": "Philosophy", "kind": "primary_text"},
    {"topic": "Aristotle Nicomachean Ethics", "field": "Philosophy", "kind": "primary_text"},
    {"topic": "Maimonides Guide for the Perplexed", "field": "Philosophy", "kind": "primary_text"},
    {"topic": "Al-Ghazali Incoherence of the Philosophers", "field": "Philosophy", "kind": "primary_text"},
    {"topic": "Ibn Khaldun Muqaddimah", "field": "History", "kind": "primary_text"},
    {"topic": "Kant Critique of Pure Reason", "field": "Philosophy", "kind": "primary_text"},
    {"topic": "Darwin Origin of Species", "field": "Biology", "kind": "book"},
    {"topic": "history of the translation movement Baghdad", "field": "History", "kind": "book"},
    {"topic": "Thomas Kuhn structure of scientific revolutions", "field": "Philosophy", "kind": "book"},
    {"topic": "Ludwik Fleck genesis of a scientific fact", "field": "Philosophy", "kind": "book"},
]


async def seed_topic(topic: str, field: str, kind: str, limit: int = 15) -> dict:
    """Seed cultural works for one topic from the Internet Archive."""
    from backend.integrations.archive_org import search_archive, get_fulltext_availability
    from backend.core.fields import normalize_field

    records = await search_archive(topic, limit=limit, media_type="texts")
    inserted, concepts_made = 0, 0

    for r in records:
        ident = r.get("external_id")
        if not ident:
            continue
        # Skip if we already have this archive item (external_id in openalex_id slot)
        existing = supabase_get("papers", {"openalex_id": f"eq.ia_{ident}", "select": "id"})
        if existing:
            continue

        # Full-text availability → reading room
        avail = await get_fulltext_availability(ident)

        paper_row = {
            "openalex_id": f"ia_{ident}",   # namespaced so it never collides with OpenAlex
            "title": r.get("title", "")[:500],
            "authors": json.dumps(r.get("authors", [])),
            "publication_year": r.get("publication_year"),
            "abstract": r.get("abstract", ""),
            "subfield": field,
            "field": normalize_field(field) or field,
            "source_journal": "Internet Archive",
            "cited_by_count": r.get("cited_by_count", 0),
            "analysis_model": "archive_org_cultural",
            "work_kind": kind,
            "external_url": avail.get("read_url") or r.get("url"),
            "has_fulltext": avail.get("has_fulltext", False),
        }
        result = supabase_post("papers", paper_row)
        if not result:
            continue
        paper_id = result[0]["id"]
        inserted += 1

        # Concepts from subject tags (free) — a real starter graph, no LLM
        for subj in (r.get("subjects") or [])[:6]:
            if not subj or len(str(subj)) < 3:
                continue
            norm = normalize_name(str(subj))
            existing_c = supabase_get("concepts", {"normalized_name": f"eq.{norm}", "select": "id"})
            if existing_c:
                cid = existing_c[0]["id"]
            else:
                created = supabase_post("concepts", {
                    "name": str(subj)[:200], "normalized_name": norm,
                    "type": "paradigm", "confidence": 0.5,
                    "definition_source": "internet_archive",
                    "consensus_status": "unverified",   # cultural tag, not academic base
                })
                if not created:
                    continue
                cid = created[0]["id"]
                concepts_made += 1
            supabase_post("paper_concepts", {
                "paper_id": paper_id, "concept_id": cid,
                "relevance": 0.6, "well_established": True,
            })

    return {"topic": topic, "inserted": inserted, "concepts_made": concepts_made}


async def main():
    parser = argparse.ArgumentParser(description="Seed cultural memory from the Internet Archive")
    parser.add_argument("--topic", default=None)
    parser.add_argument("--field", default="History")
    parser.add_argument("--kind", default="book", choices=["book", "primary_text", "historical_document", "essay"])
    parser.add_argument("--limit", type=int, default=15)
    parser.add_argument("--curated", action="store_true", help="Seed the curated history-of-ideas set")
    args = parser.parse_args()

    if not SUPABASE_URL:
        print("ERROR: SUPABASE_URL / SUPABASE_SERVICE_KEY missing"); sys.exit(1)
    init_supabase_headers()

    if args.curated:
        totals = {"inserted": 0, "concepts_made": 0}
        for item in CURATED:
            r = await seed_topic(item["topic"], item["field"], item["kind"], limit=8)
            print(f"  {item['topic'][:50]}: +{r['inserted']} works, +{r['concepts_made']} concepts")
            totals["inserted"] += r["inserted"]
            totals["concepts_made"] += r["concepts_made"]
        print(f"\nCurated cultural seed: {totals}")
    elif args.topic:
        r = await seed_topic(args.topic, args.field, args.kind, args.limit)
        print(json.dumps(r, indent=2))
    else:
        parser.error("Specify --topic or --curated")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
