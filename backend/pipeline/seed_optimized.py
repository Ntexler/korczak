"""
Optimized Graph Seeding Pipeline — Haiku-first with syllabus-driven discovery.

3 modes:
  1. --domain: Seed from OpenAlex by topic (same as seed_graph but 70% cheaper with Haiku)
  2. --syllabus: Pull readings from syllabi sources → find in OpenAlex → analyze
  3. --all-fields: Seed all 28 core fields from OpenAlex

Cost: ~$0.009/paper (Haiku) vs ~$0.03/paper (Sonnet)
       With Batch API: ~$0.005/paper

Usage:
  python -m backend.pipeline.seed_optimized --domain anthropology --limit 500
  python -m backend.pipeline.seed_optimized --domain anthropology --limit 2500 --budget 30
  python -m backend.pipeline.seed_optimized --syllabus --sources mit_ocw,open_syllabus
  python -m backend.pipeline.seed_optimized --all-fields --limit 500 --budget 200
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

import httpx
from dotenv import load_dotenv

load_dotenv()

# --- Config ---

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OPENALEX_BASE = "https://api.openalex.org"
ANTHROPIC_API = "https://api.anthropic.com/v1/messages"

# Haiku pricing (70% cheaper than Sonnet)
HAIKU_INPUT_COST = 0.80 / 1_000_000
HAIKU_OUTPUT_COST = 4.0 / 1_000_000
SONNET_INPUT_COST = 3.0 / 1_000_000
SONNET_OUTPUT_COST = 15.0 / 1_000_000

budget_spent = 0.0
budget_limit = 50.0
papers_analyzed = 0

# Supabase REST helpers
HEADERS_SUPABASE = {}

def init_supabase_headers():
    global HEADERS_SUPABASE
    HEADERS_SUPABASE = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }

# All 28 core fields with OpenAlex topic IDs
# Extended from the original 6 domains
DOMAINS = {
    # Original 6
    "anthropology": {"topic_id": "https://openalex.org/T10149", "label": "Anthropology"},
    "sleep": {"topic_id": "https://openalex.org/T10985", "label": "Sleep & Cognition"},
    "cognitive_science": {"topic_id": "https://openalex.org/T10466", "label": "Cognitive Science"},
    "philosophy": {"topic_id": "https://openalex.org/T11618", "label": "Philosophy"},
    "linguistics": {"topic_id": "https://openalex.org/T10641", "label": "Linguistics"},
    "sociology": {"topic_id": "https://openalex.org/T10276", "label": "Sociology"},
    # Extended fields
    "psychology": {"topic_id": "https://openalex.org/T10401", "label": "Psychology"},
    "economics": {"topic_id": "https://openalex.org/T10422", "label": "Economics"},
    "political_science": {"topic_id": "https://openalex.org/T10394", "label": "Political Science"},
    "history": {"topic_id": "https://openalex.org/T10555", "label": "History"},
    "biology": {"topic_id": "https://openalex.org/T10013", "label": "Biology"},
    "neuroscience": {"topic_id": "https://openalex.org/T10233", "label": "Neuroscience"},
    "physics": {"topic_id": "https://openalex.org/T10071", "label": "Physics"},
    "mathematics": {"topic_id": "https://openalex.org/T10053", "label": "Mathematics"},
    "computer_science": {"topic_id": "https://openalex.org/T10300", "label": "Computer Science"},
    "medicine": {"topic_id": "https://openalex.org/T10164", "label": "Medicine"},
    "education": {"topic_id": "https://openalex.org/T10512", "label": "Education"},
    "law": {"topic_id": "https://openalex.org/T10621", "label": "Law"},
    "environmental_science": {"topic_id": "https://openalex.org/T10109", "label": "Environmental Science"},
    "geography": {"topic_id": "https://openalex.org/T10488", "label": "Geography"},
    "gender_studies": {"topic_id": "https://openalex.org/T12035", "label": "Gender Studies"},
    "religious_studies": {"topic_id": "https://openalex.org/T11498", "label": "Religious Studies"},
    "media_studies": {"topic_id": "https://openalex.org/T10834", "label": "Media Studies"},
    "business": {"topic_id": "https://openalex.org/T10318", "label": "Business"},
    "climate_science": {"topic_id": "https://openalex.org/T10137", "label": "Climate Science"},
}

from backend.prompts.paper_analysis import ANALYSIS_PROMPT


# --- OpenAlex ---

def fetch_openalex_page(topic_id: str, per_page: int = 50, cursor: str = "*") -> dict:
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
    email = os.getenv("OPENALEX_EMAIL")
    if email:
        params["mailto"] = email
    resp = httpx.get(f"{OPENALEX_BASE}/works", params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def search_openalex_by_title(title: str) -> dict | None:
    """Search OpenAlex by paper title. Returns first match or None."""
    params = {
        "search": title,
        "per_page": 3,
        "select": (
            "id,title,authorships,publication_year,abstract_inverted_index,"
            "cited_by_count,doi,primary_location,topics"
        ),
    }
    email = os.getenv("OPENALEX_EMAIL")
    if email:
        params["mailto"] = email
    try:
        resp = httpx.get(f"{OPENALEX_BASE}/works", params=params, timeout=15)
        if resp.status_code == 200:
            results = resp.json().get("results", [])
            if results:
                return results[0]
    except Exception:
        pass
    return None


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


# --- Claude Analysis (Haiku-first) ---

def analyze_paper_haiku(title: str, authors_str: str, year: int, abstract: str) -> dict | None:
    """Analyze with Haiku (70% cheaper). Same prompt, lighter model."""
    global budget_spent, papers_analyzed

    if not abstract or len(abstract) < 50:
        return None

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
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 2000,
        "temperature": 0.2,
        "messages": [{"role": "user", "content": prompt}],
    }

    try:
        resp = httpx.post(ANTHROPIC_API, json=body, headers=headers, timeout=60)

        if resp.status_code == 429:
            retry_after = int(resp.headers.get("retry-after", 30))
            print(f"    Rate limited — waiting {retry_after}s...")
            time.sleep(retry_after)
            resp = httpx.post(ANTHROPIC_API, json=body, headers=headers, timeout=60)
        if resp.status_code in (402, 529):
            print(f"\n*** CREDITS EXHAUSTED (HTTP {resp.status_code}) ***")
            return "STOP"

        resp.raise_for_status()
        data = resp.json()
        text = data["content"][0]["text"]

        usage = data.get("usage", {})
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        call_cost = (input_tokens * HAIKU_INPUT_COST) + (output_tokens * HAIKU_OUTPUT_COST)
        budget_spent += call_cost
        papers_analyzed += 1

        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        return json.loads(text.strip())

    except httpx.HTTPStatusError as e:
        if e.response.status_code in (402, 529):
            return "STOP"
        print(f"    Analysis error: {e}")
        return None
    except httpx.ReadTimeout:
        print(f"    Timeout — skipping")
        return None
    except Exception as e:
        print(f"    Analysis error: {e}")
        return None


# --- Supabase ---

def supabase_post(table: str, data: dict | list) -> dict | list | None:
    resp = httpx.post(
        f"{SUPABASE_URL}/rest/v1/{table}",
        json=data, headers=HEADERS_SUPABASE, timeout=15,
    )
    if resp.status_code in (200, 201):
        return resp.json()
    elif resp.status_code == 409:
        return None
    else:
        print(f"    DB error ({table}): {resp.status_code} {resp.text[:150]}")
        return None


def supabase_get(table: str, params: dict) -> list:
    resp = httpx.get(
        f"{SUPABASE_URL}/rest/v1/{table}",
        params=params,
        headers={**HEADERS_SUPABASE, "Prefer": ""},
        timeout=15,
    )
    return resp.json() if resp.status_code == 200 else []


def normalize_name(name: str) -> str:
    return re.sub(r"[^a-z0-9\s]", "", name.lower()).strip()


def get_or_create_concept(concept_data: dict) -> str | None:
    norm = normalize_name(concept_data["name"])
    existing = supabase_get("concepts", {"normalized_name": f"eq.{norm}", "select": "id"})
    if existing:
        return existing[0]["id"]
    row = {
        "name": concept_data["name"],
        "normalized_name": norm,
        "type": concept_data.get("type", "phenomenon"),
        "definition": concept_data.get("definition"),
        "confidence": 0.5,
    }
    result = supabase_post("concepts", row)
    return result[0]["id"] if result else None


def insert_paper_and_analysis(paper: dict, analysis: dict, model_name: str = "claude-haiku-4-5-20251001") -> str | None:
    try:
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
            "analysis_model": model_name,
            "analyzed_at": datetime.now(tz=timezone.utc).isoformat(),
        }

        result = supabase_post("papers", paper_row)
        if not result:
            return None
        paper_id = result[0]["id"]

        concept_ids = {}
        for c in analysis.get("concepts", []):
            cid = get_or_create_concept(c)
            if cid:
                concept_ids[c["name"]] = cid
                supabase_post("paper_concepts", {
                    "paper_id": paper_id,
                    "concept_id": cid,
                    "novelty_in_paper": c.get("novelty_at_time", "low"),
                    "well_established": c.get("well_established", True),
                })

        for cl in analysis.get("claims", []):
            supabase_post("claims", {
                "paper_id": paper_id,
                "claim_text": cl["claim"],
                "evidence_type": cl.get("evidence_type"),
                "strength": cl.get("strength", "moderate"),
                "testable": cl.get("testable", False),
            })

        for rel in analysis.get("relationships", []):
            from_id = concept_ids.get(rel.get("from", "")) or get_or_create_concept({"name": rel["from"], "type": "phenomenon"})
            to_id = concept_ids.get(rel.get("to", "")) or get_or_create_concept({"name": rel["to"], "type": "phenomenon"})
            if from_id and to_id:
                supabase_post("relationships", {
                    "source_type": "concept", "source_id": from_id,
                    "target_type": "concept", "target_id": to_id,
                    "relationship_type": rel.get("type", "BUILDS_ON"),
                    "confidence": rel.get("confidence", 0.5),
                    "explanation": rel.get("explanation"),
                    "paper_id": paper_id,
                })

        return paper_id
    except Exception as e:
        print(f"    Insert error: {e}")
        return None


def paper_exists(openalex_id: str) -> bool:
    return bool(supabase_get("papers", {"openalex_id": f"eq.{openalex_id}", "select": "id"}))


# --- Mode 1: Domain Seeding (Haiku) ---

def seed_domain(domain_key: str, limit: int):
    domain = DOMAINS[domain_key]
    print(f"\n{'='*60}")
    print(f"SEEDING: {domain['label']} (Haiku)")
    print(f"Target: {limit} papers | Budget: ${budget_limit:.2f}")
    print(f"{'='*60}")

    cursor = "*"
    inserted = 0
    skipped = 0
    errors = 0
    consecutive_skips = 0

    while inserted < limit:
        if budget_spent >= budget_limit:
            print(f"\n*** BUDGET LIMIT ***")
            break

        try:
            data = fetch_openalex_page(domain["topic_id"], min(50, limit - inserted + 10), cursor)
        except Exception as e:
            print(f"  OpenAlex error: {e}")
            break

        results = data.get("results", [])
        cursor = data.get("meta", {}).get("next_cursor")
        if not results or not cursor:
            print("  No more results")
            break

        for raw in results:
            if inserted >= limit or budget_spent >= budget_limit:
                break

            paper = normalize_paper(raw)
            if paper_exists(paper["openalex_id"]):
                skipped += 1
                consecutive_skips += 1
                if consecutive_skips >= 200:
                    print(f"  200 consecutive skips — moving on")
                    return inserted
                continue

            if not paper["abstract"] or len(paper["abstract"]) < 50:
                skipped += 1
                continue

            consecutive_skips = 0
            authors_str = ", ".join(a["name"] for a in paper["authors"][:5])
            analysis = analyze_paper_haiku(paper["title"], authors_str, paper["publication_year"], paper["abstract"])

            if analysis == "STOP":
                return inserted
            if analysis and not isinstance(analysis, str):
                pid = insert_paper_and_analysis(paper, analysis)
                if pid:
                    inserted += 1
                    n_c = len(analysis.get("concepts", []))
                    if inserted % 10 == 0 or inserted <= 5:
                        print(f"  [{inserted}/{limit}] {paper['title'][:50]}... ({n_c} concepts) ${budget_spent:.3f}")
                else:
                    errors += 1
            else:
                errors += 1

            time.sleep(0.3)  # Haiku is faster, can reduce sleep
        time.sleep(0.2)

    print(f"\n  Done: {inserted} inserted, {skipped} skipped, {errors} errors, ${budget_spent:.3f}")
    return inserted


# --- Mode 2: Syllabus-Driven Discovery ---

def seed_from_syllabi(sources: list[str]):
    """Pull readings from existing syllabi, find them in OpenAlex, analyze with Haiku."""
    print(f"\n{'='*60}")
    print(f"SYLLABUS-DRIVEN SEEDING")
    print(f"Sources: {', '.join(sources)}")
    print(f"{'='*60}")

    # Get unmatched readings from syllabus_readings
    readings = supabase_get("syllabus_readings", {
        "paper_id": "is.null",
        "select": "id,external_title,external_authors,external_doi,external_year,syllabus_id",
        "limit": "500",
    })

    if not readings:
        print("  No unmatched readings found. Run scrapers first:")
        print("    python -m backend.pipeline.scrape_mit_ocw")
        print("    python -m backend.pipeline.scrape_open_syllabus")
        return 0

    print(f"  Found {len(readings)} unmatched readings to process")

    inserted = 0
    matched = 0
    not_found = 0

    for i, reading in enumerate(readings):
        if budget_spent >= budget_limit:
            print(f"\n*** BUDGET LIMIT ***")
            break

        title = reading.get("external_title", "")
        doi = reading.get("external_doi")

        if not title and not doi:
            continue

        # Try to find in OpenAlex
        raw = None
        if doi:
            try:
                resp = httpx.get(f"{OPENALEX_BASE}/works/doi:{doi}", timeout=10)
                if resp.status_code == 200:
                    raw = resp.json()
            except Exception:
                pass

        if not raw and title:
            raw = search_openalex_by_title(title)

        if not raw:
            not_found += 1
            if i < 10 or i % 50 == 0:
                print(f"  [{i+1}] Not found: {title[:50]}...")
            continue

        paper = normalize_paper(raw)

        if paper_exists(paper["openalex_id"]):
            # Already in DB — just link the reading
            existing = supabase_get("papers", {
                "openalex_id": f"eq.{paper['openalex_id']}",
                "select": "id",
            })
            if existing:
                # Update the reading with the paper_id
                httpx.patch(
                    f"{SUPABASE_URL}/rest/v1/syllabus_readings?id=eq.{reading['id']}",
                    json={"paper_id": existing[0]["id"], "match_confidence": 0.9},
                    headers=HEADERS_SUPABASE,
                    timeout=10,
                )
                matched += 1
            continue

        if not paper["abstract"] or len(paper["abstract"]) < 50:
            not_found += 1
            continue

        # Analyze with Haiku
        authors_str = ", ".join(a["name"] for a in paper["authors"][:5])
        analysis = analyze_paper_haiku(paper["title"], authors_str, paper["publication_year"], paper["abstract"])

        if analysis == "STOP":
            break
        if analysis and not isinstance(analysis, str):
            pid = insert_paper_and_analysis(paper, analysis)
            if pid:
                inserted += 1
                # Link the reading
                httpx.patch(
                    f"{SUPABASE_URL}/rest/v1/syllabus_readings?id=eq.{reading['id']}",
                    json={"paper_id": pid, "match_confidence": 0.95},
                    headers=HEADERS_SUPABASE,
                    timeout=10,
                )
                if inserted % 10 == 0 or inserted <= 5:
                    print(f"  [{inserted}] {paper['title'][:50]}... ${budget_spent:.3f}")

        time.sleep(0.3)

    print(f"\n  Done: {inserted} new papers, {matched} linked, {not_found} not found, ${budget_spent:.3f}")
    return inserted


# --- Main ---

def main():
    global budget_limit, budget_spent

    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Optimized Korczak graph seeding (Haiku)")
    parser.add_argument("--domain", choices=list(DOMAINS.keys()), help="Single domain to seed")
    parser.add_argument("--all-fields", action="store_true", help="Seed all 25 fields")
    parser.add_argument("--syllabus", action="store_true", help="Seed from syllabus readings")
    parser.add_argument("--sources", default="mit_ocw,open_syllabus", help="Syllabus sources (comma-separated)")
    parser.add_argument("--limit", type=int, default=500, help="Papers per domain")
    parser.add_argument("--budget", type=float, default=50.0, help="Max budget in USD")
    args = parser.parse_args()

    budget_limit = args.budget

    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        print("ERROR: Set SUPABASE_URL and SUPABASE_SERVICE_KEY in .env")
        sys.exit(1)
    if not ANTHROPIC_API_KEY:
        print("ERROR: Set ANTHROPIC_API_KEY in .env")
        sys.exit(1)

    init_supabase_headers()

    total = 0

    if args.syllabus:
        sources = [s.strip() for s in args.sources.split(",")]
        total = seed_from_syllabi(sources)

    elif args.all_fields:
        print(f"Seeding ALL {len(DOMAINS)} fields, {args.limit} papers each")
        print(f"Estimated cost: ~${len(DOMAINS) * args.limit * 0.009:.0f}")
        print(f"Budget: ${budget_limit:.2f}")
        for key in DOMAINS:
            if budget_spent >= budget_limit:
                print(f"\n*** Budget exhausted — skipping remaining fields ***")
                break
            total += seed_domain(key, args.limit)

    elif args.domain:
        total = seed_domain(args.domain, args.limit)

    else:
        parser.error("Specify --domain, --all-fields, or --syllabus")

    print(f"\n{'='*60}")
    print(f"TOTAL: {total} papers seeded")
    print(f"COST:  ${budget_spent:.3f} / ${budget_limit:.2f}")
    print(f"RATE:  ${budget_spent/max(papers_analyzed,1):.4f}/paper")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
