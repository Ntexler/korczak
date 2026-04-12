"""
Phase 1b — Graph Seeding Pipeline
Fetches papers from OpenAlex, analyzes with Claude, inserts into Supabase.

Usage:
  python -m backend.pipeline.seed_graph --domain anthropology --limit 100
  python -m backend.pipeline.seed_graph --domain sleep --limit 100
  python -m backend.pipeline.seed_graph --all --limit 2500
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime

import httpx
from dotenv import load_dotenv

load_dotenv()

# --- Config ---

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OPENALEX_BASE = "https://api.openalex.org"
ANTHROPIC_API = "https://api.anthropic.com/v1/messages"

DOMAINS = {
    "anthropology": {
        "topic_id": "https://openalex.org/T10149",
        "label": "Anthropological Studies and Insights",
        "target": 2500,
    },
    "sleep": {
        "topic_id": "https://openalex.org/T10985",
        "label": "Sleep and Wakefulness Research",
        "target": 2500,
    },
    "cognitive_science": {
        "topic_id": "https://openalex.org/T10466",
        "label": "Cognitive Science and Decision Making",
        "target": 2500,
    },
    "philosophy_of_mind": {
        "topic_id": "https://openalex.org/T11618",
        "label": "Philosophy of Mind and Consciousness",
        "target": 2500,
    },
    "linguistics": {
        "topic_id": "https://openalex.org/T10641",
        "label": "Linguistics and Language Evolution",
        "target": 2500,
    },
    "sociology": {
        "topic_id": "https://openalex.org/T10276",
        "label": "Sociology and Social Theory",
        "target": 2500,
    },
}

# --- Budget Tracking ---
COST_PER_INPUT_TOKEN = 3.0 / 1_000_000   # Sonnet input
COST_PER_OUTPUT_TOKEN = 15.0 / 1_000_000  # Sonnet output
budget_spent = 0.0
budget_limit = 50.0

# Supabase REST helpers
HEADERS_SUPABASE = {
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

from backend.prompts.paper_analysis import ANALYSIS_PROMPT


# --- OpenAlex ---

def fetch_openalex_page(topic_id: str, per_page: int = 50, cursor: str = "*") -> dict:
    """Fetch one page of papers from OpenAlex."""
    params = {
        "filter": (
            f"topics.id:{topic_id},"
            "has_abstract:true,language:en,type:article,"
            "from_publication_date:2015-01-01"
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

    resp = httpx.get(f"{OPENALEX_BASE}/works", params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


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


# --- Claude Analysis ---

def analyze_paper(title: str, authors_str: str, year: int, abstract: str) -> dict | None:
    """Analyze a paper with Claude. Returns parsed JSON or None on failure."""
    global budget_spent

    if not abstract or len(abstract) < 50:
        return None

    # Budget check
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
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 2000,
        "temperature": 0.2,
        "messages": [{"role": "user", "content": prompt}],
    }

    try:
        resp = httpx.post(ANTHROPIC_API, json=body, headers=headers, timeout=60)

        # Handle credit/rate limit errors
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("retry-after", 30))
            print(f"    Rate limited — waiting {retry_after}s...")
            time.sleep(retry_after)
            resp = httpx.post(ANTHROPIC_API, json=body, headers=headers, timeout=60)
        if resp.status_code in (402, 529):
            print(f"\n*** CREDITS EXHAUSTED (HTTP {resp.status_code}) — stopping gracefully ***")
            return "STOP"

        resp.raise_for_status()
        data = resp.json()
        text = data["content"][0]["text"]

        # Track cost
        usage = data.get("usage", {})
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        call_cost = (input_tokens * COST_PER_INPUT_TOKEN) + (output_tokens * COST_PER_OUTPUT_TOKEN)
        budget_spent += call_cost

        # Parse JSON from response
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        return json.loads(text.strip())
    except httpx.HTTPStatusError as e:
        if e.response.status_code in (402, 529):
            print(f"\n*** CREDITS EXHAUSTED — stopping gracefully ***")
            return "STOP"
        print(f"    Analysis error: {e}")
        return None
    except Exception as e:
        print(f"    Analysis error: {e}")
        return None


# --- Supabase Inserts ---

def supabase_post(table: str, data: dict | list) -> dict | list | None:
    """Insert into Supabase via REST API."""
    resp = httpx.post(
        f"{SUPABASE_URL}/rest/v1/{table}",
        json=data,
        headers=HEADERS_SUPABASE,
        timeout=15,
    )
    if resp.status_code in (200, 201):
        return resp.json()
    elif resp.status_code == 409:
        return None  # Duplicate, skip
    else:
        print(f"    Supabase error ({table}): {resp.status_code} {resp.text[:200]}")
        return None


def supabase_get(table: str, params: dict) -> list:
    """Query Supabase via REST API."""
    resp = httpx.get(
        f"{SUPABASE_URL}/rest/v1/{table}",
        params=params,
        headers={**HEADERS_SUPABASE, "Prefer": ""},
        timeout=15,
    )
    if resp.status_code == 200:
        return resp.json()
    return []


def normalize_name(name: str) -> str:
    """Normalize concept name for dedup."""
    return re.sub(r"[^a-z0-9\s]", "", name.lower()).strip()


def get_or_create_concept(concept_data: dict) -> str | None:
    """Find existing concept by normalized name or create new one."""
    norm = normalize_name(concept_data["name"])

    # Check if exists
    existing = supabase_get("concepts", {
        "normalized_name": f"eq.{norm}",
        "select": "id",
    })
    if existing:
        return existing[0]["id"]

    # Create new
    row = {
        "name": concept_data["name"],
        "normalized_name": norm,
        "type": concept_data.get("type", "phenomenon"),
        "definition": concept_data.get("definition"),
        "confidence": 0.5,
    }
    result = supabase_post("concepts", row)
    return result[0]["id"] if result else None


def insert_paper_and_analysis(paper: dict, analysis: dict) -> str | None:
    """Insert paper + its concepts, claims, relationships into Supabase."""
    try:
        return _insert_paper_and_analysis(paper, analysis)
    except Exception as e:
        print(f"    Insert error: {e}")
        return None


def _insert_paper_and_analysis(paper: dict, analysis: dict) -> str | None:
    """Inner insert logic."""

    # 1. Insert paper
    authors_str = ", ".join(a["name"] for a in paper["authors"][:5])
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
        "analysis_model": "claude-sonnet-4-20250514",
        "analyzed_at": datetime.now(tz=__import__('datetime').timezone.utc).isoformat(),
    }

    result = supabase_post("papers", paper_row)
    if not result:
        return None
    paper_id = result[0]["id"]

    # 2. Insert concepts and link to paper
    concept_ids = {}
    for c in analysis.get("concepts", []):
        cid = get_or_create_concept(c)
        if cid:
            concept_ids[c["name"]] = cid
            # Link paper ↔ concept
            supabase_post("paper_concepts", {
                "paper_id": paper_id,
                "concept_id": cid,
                "novelty_in_paper": c.get("novelty_at_time", "low"),
                "well_established": c.get("well_established", True),
            })

    # 3. Insert claims
    for cl in analysis.get("claims", []):
        supabase_post("claims", {
            "paper_id": paper_id,
            "claim_text": cl["claim"],
            "evidence_type": cl.get("evidence_type"),
            "strength": cl.get("strength", "moderate"),
            "testable": cl.get("testable", False),
        })

    # 4. Insert relationships (concept-to-concept)
    for rel in analysis.get("relationships", []):
        from_name = rel.get("from", "")
        to_name = rel.get("to", "")
        # Try to match to known concepts, or create them
        from_id = concept_ids.get(from_name) or get_or_create_concept({"name": from_name, "type": "phenomenon"})
        to_id = concept_ids.get(to_name) or get_or_create_concept({"name": to_name, "type": "phenomenon"})

        if from_id and to_id:
            supabase_post("relationships", {
                "source_type": "concept",
                "source_id": from_id,
                "target_type": "concept",
                "target_id": to_id,
                "relationship_type": rel.get("type", "BUILDS_ON"),
                "confidence": rel.get("confidence", 0.5),
                "explanation": rel.get("explanation"),
                "paper_id": paper_id,
            })

    return paper_id


# --- Main Pipeline ---

def seed_domain(domain_key: str, limit: int, skip_analysis: bool = False):
    """Seed papers from one domain."""
    domain = DOMAINS[domain_key]
    print(f"\n{'='*60}")
    print(f"SEEDING: {domain['label']}")
    print(f"Target: {limit} papers")
    print(f"{'='*60}")

    cursor = "*"
    total_inserted = 0
    total_analyzed = 0
    total_skipped = 0
    total_errors = 0
    batch_num = 0

    consecutive_skips = 0
    max_consecutive_skips = 200  # Stop if 200 papers in a row are all duplicates

    while total_inserted < limit:
        batch_num += 1
        per_page = min(50, limit - total_inserted + 10)  # fetch a few extra to account for skips
        print(f"\n--- Batch {batch_num} (fetching {per_page}) ---")

        try:
            data = fetch_openalex_page(domain["topic_id"], per_page, cursor)
        except Exception as e:
            print(f"  OpenAlex error: {e}")
            break

        results = data.get("results", [])
        cursor = data.get("meta", {}).get("next_cursor")

        if not results or not cursor:
            print("  No more results from OpenAlex")
            break

        for i, raw in enumerate(results):
            paper = normalize_paper(raw)

            # Skip if already in DB
            existing = supabase_get("papers", {
                "openalex_id": f"eq.{paper['openalex_id']}",
                "select": "id",
            })
            if existing:
                total_skipped += 1
                consecutive_skips += 1
                if consecutive_skips >= max_consecutive_skips:
                    print(f"  Skipped {consecutive_skips} in a row — all existing, moving to next domain")
                    return total_inserted
                continue

            # Skip if no abstract
            if not paper["abstract"] or len(paper["abstract"]) < 50:
                total_skipped += 1
                continue

            consecutive_skips = 0  # reset on new paper found

            # Budget check
            if budget_spent >= budget_limit:
                print(f"\n*** BUDGET LIMIT (${budget_spent:.2f}/${budget_limit:.2f}) ***")
                return total_inserted

            title_short = paper["title"][:55] if paper["title"] else "?"
            print(f"  [{total_inserted+1}/{limit}] {title_short}...")

            if skip_analysis:
                # Insert paper without analysis (for testing pipeline)
                paper_row = {
                    "openalex_id": paper["openalex_id"],
                    "title": paper["title"],
                    "authors": json.dumps(paper["authors"]),
                    "publication_year": paper["publication_year"],
                    "abstract": paper["abstract"],
                    "doi": paper.get("doi"),
                    "cited_by_count": paper["cited_by_count"],
                    "source_journal": paper.get("source_journal"),
                }
                result = supabase_post("papers", paper_row)
                if result:
                    total_inserted += 1
                else:
                    total_errors += 1
            else:
                # Analyze with Claude
                authors_str = ", ".join(a["name"] for a in paper["authors"][:5])
                analysis = analyze_paper(
                    paper["title"], authors_str,
                    paper["publication_year"], paper["abstract"],
                )

                if analysis == "STOP":
                    print(f"\nStopping — credits exhausted after {total_inserted} papers.")
                    return total_inserted

                if analysis and not isinstance(analysis, str) and not analysis.get("parse_error"):
                    total_analyzed += 1
                    pid = insert_paper_and_analysis(paper, analysis)
                    if pid:
                        total_inserted += 1
                        n_c = len(analysis.get("concepts", []))
                        n_r = len(analysis.get("relationships", []))
                        print(f"    -> {n_c} concepts, {n_r} rels | ${budget_spent:.2f}/${budget_limit:.2f}")
                    else:
                        total_errors += 1
                else:
                    total_errors += 1
                    print(f"    -> Analysis failed")

                # Rate limit: Claude API
                time.sleep(0.5)

        # Rate limit: OpenAlex
        time.sleep(0.2)

    print(f"\n{'='*60}")
    print(f"DONE: {domain['label']}")
    print(f"  Inserted: {total_inserted}")
    print(f"  Analyzed: {total_analyzed}")
    print(f"  Skipped:  {total_skipped}")
    print(f"  Errors:   {total_errors}")
    print(f"  Budget:   ${budget_spent:.2f} / ${budget_limit:.2f}")
    return total_inserted


def main():
    global budget_limit, budget_spent

    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Seed Korczak knowledge graph")
    parser.add_argument("--domain", choices=list(DOMAINS.keys()), help="Domain to seed")
    parser.add_argument("--all", action="store_true", help="Seed all domains")
    parser.add_argument("--limit", type=int, default=2500, help="Papers per domain")
    parser.add_argument("--budget", type=float, default=50.0, help="Max budget in USD")
    parser.add_argument("--skip-analysis", action="store_true", help="Insert papers without Claude analysis (testing)")
    args = parser.parse_args()

    budget_limit = args.budget

    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        print("ERROR: Set SUPABASE_URL and SUPABASE_SERVICE_KEY in .env")
        sys.exit(1)
    if not args.skip_analysis and not ANTHROPIC_API_KEY:
        print("ERROR: Set ANTHROPIC_API_KEY in .env")
        sys.exit(1)

    domains_to_seed = list(DOMAINS.keys()) if args.all else [args.domain]
    if not args.all and not args.domain:
        parser.error("Specify --domain or --all")

    print(f"Budget: ${budget_limit:.2f}")
    print(f"Domains: {', '.join(domains_to_seed)}")
    print(f"Limit per domain: {args.limit}")

    total = 0
    for d in domains_to_seed:
        if budget_spent >= budget_limit:
            print(f"\n*** Budget exhausted (${budget_spent:.2f}) — skipping {d} ***")
            break
        total += seed_domain(d, args.limit, args.skip_analysis)

    print(f"\n{'='*60}")
    print(f"TOTAL PAPERS SEEDED: {total}")
    print(f"TOTAL COST: ${budget_spent:.2f} / ${budget_limit:.2f}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
