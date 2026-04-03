"""
Multi-Source Enrichment Pipeline
Enriches papers in the DB with data from free academic sources:
  - Semantic Scholar: citations, TLDR, influential citations, citation intent
  - CrossRef: metadata verification, reference counts
  - Retraction Watch: check for retractions

Usage:
  python -m backend.pipeline.enrich_sources --source s2 --limit 100
  python -m backend.pipeline.enrich_sources --source crossref --limit 100
  python -m backend.pipeline.enrich_sources --all --limit 500
"""

import argparse
import json
import os
import sys
import time

import httpx
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

HEADERS_SUPABASE = {
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}


# --- Supabase helpers ---

def supabase_get(table: str, params: dict) -> list:
    resp = httpx.get(
        f"{SUPABASE_URL}/rest/v1/{table}",
        params=params,
        headers={**HEADERS_SUPABASE, "Prefer": ""},
        timeout=15,
    )
    return resp.json() if resp.status_code == 200 else []


def supabase_post(table: str, data: dict) -> dict | None:
    resp = httpx.post(
        f"{SUPABASE_URL}/rest/v1/{table}",
        json=data,
        headers=HEADERS_SUPABASE,
        timeout=15,
    )
    if resp.status_code in (200, 201):
        return resp.json()
    elif resp.status_code == 409:
        return None  # Duplicate
    return None


def supabase_patch(table: str, params: dict, data: dict) -> bool:
    resp = httpx.patch(
        f"{SUPABASE_URL}/rest/v1/{table}",
        params=params,
        json=data,
        headers=HEADERS_SUPABASE,
        timeout=15,
    )
    return resp.status_code in (200, 204)


def get_papers_without_source(source_name: str, limit: int) -> list:
    """Get papers that haven't been enriched by this source yet."""
    # Get papers that have DOIs (needed for lookups)
    papers = supabase_get("papers", {
        "select": "id,doi,title,openalex_id,cited_by_count",
        "doi": "not.is.null",
        "order": "cited_by_count.desc",
        "limit": str(limit * 2),  # Fetch extra since some may already be enriched
    })

    # Filter out papers already enriched by this source
    enriched_ids = set()
    evidence = supabase_get("source_evidence", {
        "select": "element_id",
        "source_name": f"eq.{source_name}",
        "element_type": "eq.paper",
    })
    for e in evidence:
        enriched_ids.add(e["element_id"])

    return [p for p in papers if p["id"] not in enriched_ids][:limit]


# =============================================
# SEMANTIC SCHOLAR
# =============================================

S2_API = "https://api.semanticscholar.org/graph/v1"
S2_FIELDS = "paperId,title,citationCount,influentialCitationCount,tldr"


def enrich_semantic_scholar(limit: int) -> int:
    """Enrich papers with Semantic Scholar data."""
    print(f"\n{'='*60}")
    print("ENRICHING: Semantic Scholar")
    print(f"{'='*60}")

    papers = get_papers_without_source("semantic_scholar_metadata", limit)
    print(f"Papers to enrich: {len(papers)}")

    enriched = 0
    for i, paper in enumerate(papers):
        doi = paper["doi"]
        if not doi:
            continue

        # Clean DOI
        doi_clean = doi.replace("https://doi.org/", "")
        title_short = paper["title"][:50] if paper["title"] else "?"
        print(f"  [{i+1}/{len(papers)}] {title_short}...")

        try:
            resp = httpx.get(
                f"{S2_API}/paper/DOI:{doi_clean}",
                params={"fields": S2_FIELDS},
                timeout=15,
            )

            if resp.status_code == 404:
                print(f"    Not found in S2")
                # Record that we checked
                supabase_post("source_evidence", {
                    "element_type": "paper",
                    "element_id": paper["id"],
                    "source_name": "semantic_scholar_metadata",
                    "signal_type": "enriches",
                    "signal_value": 0,
                    "signal_detail": json.dumps({"status": "not_found"}),
                })
                time.sleep(1)
                continue

            if resp.status_code == 429:
                wait = int(resp.headers.get("retry-after", 60))
                print(f"    Rate limited, waiting {wait}s...")
                time.sleep(wait)
                continue

            resp.raise_for_status()
            s2_data = resp.json()

            # Extract key metrics
            s2_citation_count = s2_data.get("citationCount", 0)
            influential_count = s2_data.get("influentialCitationCount", 0)
            tldr = (s2_data.get("tldr") or {}).get("text")

            # Record source evidence
            signal_detail = {
                "s2_paper_id": s2_data.get("paperId"),
                "s2_citation_count": s2_citation_count,
                "influential_citation_count": influential_count,
                "tldr": tldr,
            }

            supabase_post("source_evidence", {
                "element_type": "paper",
                "element_id": paper["id"],
                "source_name": "semantic_scholar_metadata",
                "signal_type": "enriches",
                "signal_value": min(influential_count / max(s2_citation_count, 1), 1.0),
                "signal_detail": json.dumps(signal_detail),
            })

            # Check citation count disagreement with OpenAlex
            oa_citations = paper.get("cited_by_count", 0)
            if oa_citations > 0 and s2_citation_count > 0:
                ratio = max(oa_citations, s2_citation_count) / min(oa_citations, s2_citation_count)
                if ratio > 2.0:  # More than 2x difference
                    supabase_post("source_disagreements", {
                        "element_type": "paper",
                        "element_id": paper["id"],
                        "source_a": "openalex",
                        "source_a_value": json.dumps({"citation_count": oa_citations}),
                        "source_b": "semantic_scholar",
                        "source_b_value": json.dumps({"citation_count": s2_citation_count}),
                        "disagreement_type": "citation_count",
                        "details": json.dumps({"ratio": round(ratio, 2)}),
                    })

            enriched += 1
            inf_str = f", {influential_count} influential" if influential_count else ""
            print(f"    -> S2 citations: {s2_citation_count}{inf_str}")
            if tldr:
                print(f"    -> TLDR: {tldr[:80]}...")

        except Exception as e:
            print(f"    Error: {e}")

        # S2 rate limit: 100 requests/5 min = 1 per 3s
        time.sleep(3)

    print(f"\nEnriched: {enriched}/{len(papers)}")
    return enriched


# =============================================
# CROSSREF
# =============================================

CROSSREF_API = "https://api.crossref.org/works"


def enrich_crossref(limit: int) -> int:
    """Enrich papers with CrossRef metadata verification."""
    print(f"\n{'='*60}")
    print("ENRICHING: CrossRef")
    print(f"{'='*60}")

    papers = get_papers_without_source("crossref_metadata", limit)
    print(f"Papers to enrich: {len(papers)}")

    enriched = 0
    for i, paper in enumerate(papers):
        doi = paper["doi"]
        if not doi:
            continue

        doi_clean = doi.replace("https://doi.org/", "")
        title_short = paper["title"][:50] if paper["title"] else "?"
        print(f"  [{i+1}/{len(papers)}] {title_short}...")

        try:
            resp = httpx.get(
                f"{CROSSREF_API}/{doi_clean}",
                headers={"User-Agent": "Korczak-AI/0.1 (mailto:contact@korczak.ai)"},
                timeout=15,
            )

            if resp.status_code == 404:
                print(f"    Not found in CrossRef")
                supabase_post("source_evidence", {
                    "element_type": "paper",
                    "element_id": paper["id"],
                    "source_name": "crossref_metadata",
                    "signal_type": "enriches",
                    "signal_value": 0,
                    "signal_detail": json.dumps({"status": "not_found"}),
                })
                time.sleep(1)
                continue

            resp.raise_for_status()
            cr_data = resp.json().get("message", {})

            # Extract metadata
            cr_citation_count = cr_data.get("is-referenced-by-count", 0)
            reference_count = cr_data.get("reference-count", 0)
            cr_type = cr_data.get("type", "unknown")
            publisher = cr_data.get("publisher")
            license_info = cr_data.get("license", [])
            is_open_access = any("open" in (l.get("URL", "").lower()) for l in license_info)

            signal_detail = {
                "crossref_citation_count": cr_citation_count,
                "reference_count": reference_count,
                "type": cr_type,
                "publisher": publisher,
                "is_open_access": is_open_access,
                "has_references": reference_count > 0,
                "subject": cr_data.get("subject", []),
            }

            supabase_post("source_evidence", {
                "element_type": "paper",
                "element_id": paper["id"],
                "source_name": "crossref_metadata",
                "signal_type": "confirms",
                "signal_value": 0.8 if reference_count > 0 else 0.5,
                "signal_detail": json.dumps(signal_detail),
            })

            enriched += 1
            print(f"    -> CrossRef: {cr_citation_count} citations, {reference_count} references, type={cr_type}")

        except Exception as e:
            print(f"    Error: {e}")

        # CrossRef: polite pool ~50 req/sec, but be conservative
        time.sleep(1)

    print(f"\nEnriched: {enriched}/{len(papers)}")
    return enriched


# =============================================
# RETRACTION WATCH
# =============================================

RETRACTION_API = "http://api.labs.crossref.org/works"


def check_retractions(limit: int) -> int:
    """Check papers against retraction databases."""
    print(f"\n{'='*60}")
    print("CHECKING: Retractions")
    print(f"{'='*60}")

    papers = get_papers_without_source("retraction_check", limit)
    print(f"Papers to check: {len(papers)}")

    checked = 0
    retracted = 0
    for i, paper in enumerate(papers):
        doi = paper["doi"]
        if not doi:
            continue

        doi_clean = doi.replace("https://doi.org/", "")
        title_short = paper["title"][:50] if paper["title"] else "?"

        try:
            # Use CrossRef to check for retraction notices
            resp = httpx.get(
                f"{CROSSREF_API}/{doi_clean}",
                headers={"User-Agent": "Korczak-AI/0.1 (mailto:contact@korczak.ai)"},
                timeout=15,
            )

            is_retracted = False
            if resp.status_code == 200:
                cr_data = resp.json().get("message", {})
                # Check for retraction/correction updates
                updates = cr_data.get("update-to", [])
                for update in updates:
                    if update.get("type") in ("retraction", "removal"):
                        is_retracted = True
                        break

            supabase_post("source_evidence", {
                "element_type": "paper",
                "element_id": paper["id"],
                "source_name": "retraction_check",
                "signal_type": "confirms" if not is_retracted else "contradicts",
                "signal_value": 0.0 if is_retracted else 1.0,
                "signal_detail": json.dumps({"retracted": is_retracted}),
            })

            if is_retracted:
                retracted += 1
                # Add critical quality flag
                supabase_post("quality_flags", {
                    "element_type": "paper",
                    "element_id": paper["id"],
                    "flag_type": "RETRACTED",
                    "severity": "critical",
                    "detail": f"Paper DOI {doi_clean} has been retracted",
                    "suggested_action": "Remove from graph or mark as retracted",
                })
                print(f"  [{i+1}] *** RETRACTED *** {title_short}")
            else:
                checked += 1

        except Exception as e:
            print(f"  [{i+1}] Error checking {title_short}: {e}")

        time.sleep(1)

    print(f"\nChecked: {checked}, Retracted: {retracted}")
    return checked


# =============================================
# MAIN
# =============================================

def main():
    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Enrich Korczak papers with free sources")
    parser.add_argument("--source", choices=["s2", "crossref", "retraction"], help="Source to enrich from")
    parser.add_argument("--all", action="store_true", help="Run all enrichment sources")
    parser.add_argument("--limit", type=int, default=50, help="Papers to enrich")
    args = parser.parse_args()

    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        print("ERROR: Set SUPABASE_URL and SUPABASE_SERVICE_KEY in .env")
        sys.exit(1)

    if not args.all and not args.source:
        parser.error("Specify --source or --all")

    total = 0
    if args.all or args.source == "s2":
        total += enrich_semantic_scholar(args.limit)
    if args.all or args.source == "crossref":
        total += enrich_crossref(args.limit)
    if args.all or args.source == "retraction":
        total += check_retractions(args.limit)

    print(f"\n{'='*60}")
    print(f"TOTAL ENRICHMENTS: {total}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
