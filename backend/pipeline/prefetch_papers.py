"""
Pre-fetch papers from OpenAlex and save as local JSON cache.
No API keys needed — OpenAlex is free.

This creates JSON files per field that seed_optimized.py can load
directly instead of fetching from OpenAlex at seeding time.

Usage:
  python -m backend.pipeline.prefetch_papers --all --limit 500
  python -m backend.pipeline.prefetch_papers --domain anthropology --limit 1000
"""

import argparse
import json
import os
import sys
import time

import httpx

OPENALEX_BASE = "https://api.openalex.org"
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "prefetch")

DOMAINS = {
    "anthropology": {"topic_id": "https://openalex.org/T10149", "label": "Anthropology"},
    "sleep": {"topic_id": "https://openalex.org/T10985", "label": "Sleep & Cognition"},
    "cognitive_science": {"topic_id": "https://openalex.org/T10466", "label": "Cognitive Science"},
    "philosophy": {"topic_id": "https://openalex.org/T11618", "label": "Philosophy"},
    "linguistics": {"topic_id": "https://openalex.org/T10641", "label": "Linguistics"},
    "sociology": {"topic_id": "https://openalex.org/T10276", "label": "Sociology"},
    "psychology": {"topic_id": "https://openalex.org/T10401", "label": "Psychology"},
    "economics": {"topic_id": "https://openalex.org/T10422", "label": "Economics"},
    "political_science": {"topic_id": "https://openalex.org/T10394", "label": "Political Science"},
    "history": {"topic_id": "https://openalex.org/T10555", "label": "History"},
    "biology": {"topic_id": "https://openalex.org/T10013", "label": "Biology"},
    "neuroscience": {"topic_id": "https://openalex.org/T10233", "label": "Neuroscience"},
    "computer_science": {"topic_id": "https://openalex.org/T10300", "label": "Computer Science"},
    "medicine": {"topic_id": "https://openalex.org/T10164", "label": "Medicine"},
    "education": {"topic_id": "https://openalex.org/T10512", "label": "Education"},
    "law": {"topic_id": "https://openalex.org/T10621", "label": "Law"},
    "environmental_science": {"topic_id": "https://openalex.org/T10109", "label": "Environmental Science"},
    "geography": {"topic_id": "https://openalex.org/T10488", "label": "Geography"},
    "business": {"topic_id": "https://openalex.org/T10318", "label": "Business"},
    "climate_science": {"topic_id": "https://openalex.org/T10137", "label": "Climate Science"},
}


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
            if a.get("institutions") else None
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


def fetch_domain(domain_key: str, limit: int) -> list[dict]:
    domain = DOMAINS[domain_key]
    topic_id = domain["topic_id"]
    print(f"\n  Fetching {domain['label']}...")

    papers = []
    cursor = "*"
    retries = 0

    while len(papers) < limit:
        per_page = min(50, limit - len(papers))
        params = {
            "filter": (
                f"topics.id:{topic_id},"
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

        try:
            resp = httpx.get(f"{OPENALEX_BASE}/works", params=params, timeout=30)

            if resp.status_code == 429:
                wait = int(resp.headers.get("retry-after", 5))
                print(f"    Rate limited, waiting {wait}s...")
                time.sleep(wait)
                continue

            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", [])
            cursor = data.get("meta", {}).get("next_cursor")

            if not results or not cursor:
                break

            for raw in results:
                paper = normalize_paper(raw)
                if paper["abstract"] and len(paper["abstract"]) >= 50:
                    papers.append(paper)

            if len(papers) % 100 == 0 or len(papers) >= limit:
                print(f"    {len(papers)}/{limit} papers fetched")

            retries = 0
            time.sleep(0.15)  # Be polite

        except Exception as e:
            retries += 1
            if retries >= 3:
                print(f"    Failed after 3 retries: {e}")
                break
            print(f"    Error ({e}), retrying in 3s...")
            time.sleep(3)

    return papers[:limit]


def main():
    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Pre-fetch papers from OpenAlex")
    parser.add_argument("--domain", choices=list(DOMAINS.keys()))
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--limit", type=int, default=500, help="Papers per field")
    args = parser.parse_args()

    if not args.all and not args.domain:
        parser.error("Specify --domain or --all")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    domains = list(DOMAINS.keys()) if args.all else [args.domain]

    total = 0
    for key in domains:
        papers = fetch_domain(key, args.limit)
        total += len(papers)

        outfile = os.path.join(OUTPUT_DIR, f"{key}.json")
        with open(outfile, "w", encoding="utf-8") as f:
            json.dump({
                "domain": key,
                "label": DOMAINS[key]["label"],
                "topic_id": DOMAINS[key]["topic_id"],
                "count": len(papers),
                "papers": papers,
            }, f, ensure_ascii=False, indent=2)

        print(f"  -> Saved {len(papers)} papers to {outfile}")

    print(f"\n{'='*60}")
    print(f"TOTAL: {total} papers pre-fetched across {len(domains)} fields")
    print(f"Saved to: {OUTPUT_DIR}/")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
