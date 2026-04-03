"""
Phase 0.5 — Test New Papers Analysis
Fetches 10 recent (2024-2025) anthropology papers from OpenAlex,
runs Claude analysis prompt on each, outputs results for manual review.
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    print("ERROR: Set ANTHROPIC_API_KEY in .env file")
    sys.exit(1)

OPENALEX_BASE = "https://api.openalex.org"
ANTHROPIC_API = "https://api.anthropic.com/v1/messages"

# Phase 0 prompt from spec
ANALYSIS_PROMPT = """Analyze this academic work for a knowledge graph.

WORK: {title}
AUTHORS: {authors}
YEAR: {year}
ABSTRACT: {abstract}

Extract in JSON:

1. CONCEPTS: Key concepts introduced or central to this work
   Format: [{{"name": str, "type": "theory|method|framework|phenomenon", "definition": str, "novelty_at_time": "high|medium|low"}}]

2. RELATIONSHIPS: How this work relates to other works/concepts
   Format: [{{"from": str, "to": str, "type": "BUILDS_ON|CONTRADICTS|EXTENDS|APPLIES|ANALOGOUS_TO|RESPONDS_TO", "confidence": float, "explanation": str}}]

3. CLAIMS: Central claims with evidence basis
   Format: [{{"claim": str, "evidence_type": str, "strength": "strong|moderate|weak"}}]

4. HISTORICAL_SIGNIFICANCE: Role in the field's development
   Format: {{"paradigm_shift": bool, "influenced_fields": [str], "controversy_generated": str, "lasting_impact": str}}

Return ONLY valid JSON with keys: concepts, relationships, claims, historical_significance"""


def fetch_papers(count: int = 10) -> list[dict]:
    """Fetch recent anthropology papers from OpenAlex."""
    params = {
        "filter": "topics.id:https://openalex.org/T10149,from_publication_date:2024-01-01,to_publication_date:2025-12-31,has_abstract:true,language:en,type:article",
        "sort": "cited_by_count:desc",
        "per_page": count,
        "select": "id,title,authorships,publication_year,abstract_inverted_index,cited_by_count,doi,primary_location",
    }
    print(f"Fetching {count} papers from OpenAlex...")
    resp = httpx.get(f"{OPENALEX_BASE}/works", params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    print(f"Got {len(data['results'])} papers")
    return data["results"]


def reconstruct_abstract(inverted_index: dict | None) -> str:
    """OpenAlex stores abstracts as inverted indexes — reconstruct to text."""
    if not inverted_index:
        return "No abstract available"
    word_positions = []
    for word, positions in inverted_index.items():
        for pos in positions:
            word_positions.append((pos, word))
    word_positions.sort()
    return " ".join(w for _, w in word_positions)


def extract_authors(authorships: list) -> str:
    """Extract author names from OpenAlex authorships."""
    names = []
    for a in authorships[:5]:  # limit to first 5
        name = a.get("author", {}).get("display_name", "Unknown")
        names.append(name)
    if len(authorships) > 5:
        names.append(f"et al. (+{len(authorships) - 5})")
    return ", ".join(names)


def analyze_with_claude(paper: dict) -> dict:
    """Send paper to Claude for analysis."""
    title = paper.get("title", "Unknown")
    authors = extract_authors(paper.get("authorships", []))
    year = paper.get("publication_year", "Unknown")
    abstract = reconstruct_abstract(paper.get("abstract_inverted_index"))

    prompt = ANALYSIS_PROMPT.format(
        title=title, authors=authors, year=year, abstract=abstract
    )

    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "content-type": "application/json",
        "anthropic-version": "2023-06-01",
    }
    body = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 2000,
        "messages": [{"role": "user", "content": prompt}],
    }

    resp = httpx.post(ANTHROPIC_API, json=body, headers=headers, timeout=60)
    resp.raise_for_status()
    result = resp.json()
    text = result["content"][0]["text"]

    # Try to parse JSON from response
    try:
        # Handle markdown code blocks
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        parsed = json.loads(text.strip())
    except (json.JSONDecodeError, IndexError):
        parsed = {"raw_text": text, "parse_error": True}

    return {
        "paper": {
            "title": title,
            "authors": authors,
            "year": year,
            "doi": paper.get("doi"),
            "cited_by_count": paper.get("cited_by_count", 0),
            "abstract_preview": abstract[:200] + "..." if len(abstract) > 200 else abstract,
        },
        "analysis": parsed,
    }


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    print("=" * 60)
    print("KORCZAK AI — Phase 0.5: New Papers Analysis Test")
    print("=" * 60)

    # Fetch papers
    papers = fetch_papers(10)

    results = []
    for i, paper in enumerate(papers, 1):
        title = paper.get("title", "Unknown")
        print(f"\n[{i}/10] Analyzing: {title[:70]}...")
        try:
            result = analyze_with_claude(paper)
            results.append(result)

            # Quick summary
            analysis = result["analysis"]
            if not analysis.get("parse_error"):
                n_concepts = len(analysis.get("concepts", []))
                n_rels = len(analysis.get("relationships", []))
                n_claims = len(analysis.get("claims", []))
                print(f"  -> {n_concepts} concepts, {n_rels} relationships, {n_claims} claims")
            else:
                print("  -> WARNING: Could not parse JSON response")

            # Rate limit: ~1 req/sec to be safe
            if i < 10:
                time.sleep(1)

        except Exception as e:
            print(f"  -> ERROR: {e}")
            results.append({
                "paper": {"title": title, "error": str(e)},
                "analysis": None,
            })

    # Save results
    output_path = Path("phase05_results.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n{'=' * 60}")
    print(f"Results saved to {output_path}")

    # Print summary
    successful = sum(1 for r in results if r["analysis"] and not r["analysis"].get("parse_error"))
    print(f"Successful analyses: {successful}/10")

    # Print scorecard
    print(f"\n{'=' * 60}")
    print("SCORECARD — Review each paper's analysis:")
    print("=" * 60)
    for i, r in enumerate(results, 1):
        title = r["paper"]["title"][:60]
        if r["analysis"] and not r["analysis"].get("parse_error"):
            a = r["analysis"]
            concepts = [c["name"] for c in a.get("concepts", [])[:3]]
            print(f"\n{i}. {title}")
            print(f"   Concepts: {', '.join(concepts)}")
            print(f"   Relationships: {len(a.get('relationships', []))}")
            print(f"   Claims: {len(a.get('claims', []))}")
            sig = a.get("historical_significance", {})
            if sig.get("paradigm_shift"):
                print(f"   ** PARADIGM SHIFT flagged **")
        else:
            print(f"\n{i}. {title} — FAILED")

    print(f"\n{'=' * 60}")
    print("Next: Manually review phase05_results.json")
    print("Score each paper on: accuracy, depth, relationships, insights (1-10)")
    print("Target: 8/10 average to proceed to Phase 1")


if __name__ == "__main__":
    main()
