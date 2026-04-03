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

# Phase 0.5 prompt — improved based on review of Phase 0 results
ANALYSIS_PROMPT = """Analyze this academic work for a knowledge graph. You are working from the abstract only — calibrate your confidence accordingly. Do NOT over-interpret or infer beyond what the text supports.

WORK: {title}
AUTHORS: {authors}
YEAR: {year}
ABSTRACT: {abstract}

Extract in JSON:

0. PAPER_TYPE: Classify this paper.
   Format: {{"type": "original_research|review|meta_analysis|theoretical|methodological|commentary|book_chapter", "subfield": str, "summary": str}}
   - "subfield": the specific academic subfield (e.g. "medical anthropology", not just "anthropology")
   - "summary": one sentence describing the paper's core contribution

1. CONCEPTS: Key concepts introduced or central to this work.
   Format: [{{"name": str, "type": "theory|method|framework|phenomenon|tool|metric|critique|paradigm", "definition": str, "novelty_at_time": "high|medium|low", "well_established": bool}}]
   - Use VARIED types — not everything is a "framework". A measurement tool is a "tool", a critique of existing work is a "critique", an observed pattern is a "phenomenon".
   - "well_established": true if this concept existed before this paper and is widely known in the field.
   - "novelty_at_time": "high" ONLY if this paper introduces the concept for the first time. Most concepts in most papers are "low" (using existing ideas) or "medium" (applying known ideas in a new context).

2. RELATIONSHIPS: How this work connects to other specific works, authors, or intellectual traditions.
   Format: [{{"from": str, "to": str, "type": "BUILDS_ON|CONTRADICTS|EXTENDS|APPLIES|ANALOGOUS_TO|RESPONDS_TO", "confidence": float, "explanation": str}}]
   - "confidence": 0.5-0.7 if inferred from abstract context, 0.8+ only if explicitly stated.
   - Prefer naming SPECIFIC works or authors over vague traditions (e.g. "Said's Orientalism" not "postcolonial theory").
   - Only include relationships you can justify from the abstract text.

3. CLAIMS: Central claims with evidence basis.
   Format: [{{"claim": str, "evidence_type": "empirical|theoretical|comparative|methodological|meta_analytic", "strength": "strong|moderate|weak", "testable": bool}}]
   - "testable": can this claim be empirically verified or falsified?

4. HISTORICAL_SIGNIFICANCE: Role in the field's development.
   Format: {{"paradigm_shift": bool, "influenced_fields": [str], "controversy_generated": str, "lasting_impact": str}}
   - CRITICAL: "paradigm_shift" should be TRUE only for works that fundamentally redefine how a field thinks (maybe 1-2% of all papers). A good paper with a new perspective is NOT a paradigm shift. When in doubt, set false.
   - "controversy_generated": if no clear controversy, say "none apparent from abstract"

Return ONLY valid JSON with keys: paper_type, concepts, relationships, claims, historical_significance"""


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
    paradigm_shifts = 0
    for i, r in enumerate(results, 1):
        title = r["paper"]["title"][:60]
        if r["analysis"] and not r["analysis"].get("parse_error"):
            a = r["analysis"]
            pt = a.get("paper_type", {})
            concepts = a.get("concepts", [])
            concept_types = [c.get("type", "?") for c in concepts]
            novel_count = sum(1 for c in concepts if c.get("novelty_at_time") == "high")
            established_count = sum(1 for c in concepts if c.get("well_established"))
            rels = a.get("relationships", [])
            avg_conf = sum(r.get("confidence", 0) for r in rels) / len(rels) if rels else 0
            sig = a.get("historical_significance", {})
            if sig.get("paradigm_shift"):
                paradigm_shifts += 1
            print(f"\n{i}. {title}")
            print(f"   Type: {pt.get('type', '?')} | Subfield: {pt.get('subfield', '?')}")
            print(f"   Summary: {pt.get('summary', 'N/A')}")
            print(f"   Concepts: {len(concepts)} (types: {', '.join(set(concept_types))}) | Novel: {novel_count} | Established: {established_count}")
            print(f"   Relationships: {len(rels)} (avg confidence: {avg_conf:.2f})")
            print(f"   Claims: {len(a.get('claims', []))}")
            if sig.get("paradigm_shift"):
                print(f"   ** PARADIGM SHIFT flagged **")
        else:
            print(f"\n{i}. {title} — FAILED")

    print(f"\nParadigm shifts flagged: {paradigm_shifts}/10 (expect 0-1)")

    print(f"\n{'=' * 60}")
    print("Next: Manually review phase05_results.json")
    print("Score each paper on: accuracy, depth, relationships, insights (1-10)")
    print("Target: 8/10 average to proceed to Phase 1")


if __name__ == "__main__":
    main()
