"""Korczak Learning Agent — autonomous knowledge enrichment.

An agent that goes out into the world, asks smart questions, and brings
back knowledge to enrich the graph. Runs as a background process.

What it does:
1. Scans the knowledge graph for weak spots (low confidence, few sources,
   missing connections, orphan concepts)
2. Generates targeted questions for external sources (Sci-Bot, multi-search)
3. Parses responses and extracts new claims, connections, and evidence
4. Feeds structured findings back into the knowledge graph

NOT what it does:
- Does NOT change existing confidence scores without human review
- Does NOT delete existing knowledge
- Stores findings as "pending_enrichments" for review

Usage:
  # Run one enrichment cycle
  python -m backend.agents.learning_agent --field Anthropology --limit 10

  # Or call programmatically
  results = await run_enrichment_cycle("Anthropology", limit=10)
"""

import logging
import json
import asyncio

from backend.integrations.supabase_client import get_client

logger = logging.getLogger(__name__)


async def find_weak_spots(field_name: str, limit: int = 20) -> list[dict]:
    """Find concepts that need enrichment.

    Priorities:
    1. Low source_count (< 2) — concept based on very few papers
    2. Short/empty definition (< 50 chars)
    3. No claims linked
    4. High paper_count but low confidence — important but uncertain
    5. Orphans — no relationships to other concepts
    """
    client = get_client()

    from backend.api.features import _normalize_field

    # Get field papers
    all_papers = client.table("papers").select("id, subfield").not_.is_("subfield", "null").execute()
    field_paper_ids = [
        p["id"] for p in (all_papers.data or [])
        if _normalize_field(p.get("subfield", "")) == field_name
    ]

    if not field_paper_ids:
        return []

    # Get concepts
    concept_ids = set()
    for i in range(0, len(field_paper_ids), 50):
        batch = field_paper_ids[i:i + 50]
        pc = client.table("paper_concepts").select("concept_id").in_("paper_id", batch).execute()
        for row in (pc.data or []):
            concept_ids.add(row["concept_id"])

    if not concept_ids:
        return []

    # Fetch concept details in batches
    concepts = []
    cid_list = list(concept_ids)
    for i in range(0, len(cid_list), 50):
        batch = cid_list[i:i + 50]
        result = client.table("concepts").select(
            "id, name, type, definition, paper_count, confidence, source_count"
        ).in_("id", batch).execute()
        concepts.extend(result.data or [])

    # Get relationships to detect orphans
    rels = client.table("relationships").select("source_id, target_id").execute()
    connected = set()
    for r in (rels.data or []):
        connected.add(r["source_id"])
        connected.add(r["target_id"])

    # Score each concept's need for enrichment
    weak = []
    for c in concepts:
        score = 0
        reasons = []

        # Short/empty definition
        defn = c.get("definition") or ""
        if len(defn) < 50:
            score += 3
            reasons.append("short_definition")

        # Low source count
        src_count = c.get("source_count", 1)
        if src_count < 2:
            score += 2
            reasons.append("few_sources")

        # High paper_count but low confidence
        if c.get("paper_count", 0) > 5 and c.get("confidence", 0.5) < 0.5:
            score += 3
            reasons.append("important_but_uncertain")

        # Orphan (no relationships)
        if c["id"] not in connected:
            score += 2
            reasons.append("orphan")

        if score > 0:
            weak.append({
                "concept_id": c["id"],
                "concept_name": c["name"],
                "concept_type": c.get("type", "concept"),
                "definition": defn,
                "score": score,
                "reasons": reasons,
                "paper_count": c.get("paper_count", 0),
                "confidence": c.get("confidence", 0.5),
            })

    # Sort by score (most needy first)
    weak.sort(key=lambda x: -x["score"])
    return weak[:limit]


def generate_questions(weak_spots: list[dict]) -> list[dict]:
    """Generate smart questions for each weak spot.

    Each question is tailored to what's missing.
    """
    questions = []

    for spot in weak_spots:
        name = spot["concept_name"]
        ctype = spot["concept_type"]
        reasons = spot["reasons"]

        if "short_definition" in reasons:
            questions.append({
                "concept_id": spot["concept_id"],
                "concept_name": name,
                "question": f"What is {name} in academic research? Provide a comprehensive definition with key characteristics, origins, and main proponents.",
                "purpose": "enrich_definition",
            })

        if "few_sources" in reasons:
            questions.append({
                "concept_id": spot["concept_id"],
                "concept_name": name,
                "question": f"What are the most important and influential papers about {name}? List the key studies with authors and years.",
                "purpose": "find_sources",
            })

        if "important_but_uncertain" in reasons:
            questions.append({
                "concept_id": spot["concept_id"],
                "concept_name": name,
                "question": f"What is the current scientific consensus on {name}? Is it well-established or still debated? What are the main criticisms?",
                "purpose": "assess_confidence",
            })

        if "orphan" in reasons:
            questions.append({
                "concept_id": spot["concept_id"],
                "concept_name": name,
                "question": f"How does {name} ({ctype}) relate to other concepts in the field? What does it build on, extend, or contradict?",
                "purpose": "find_connections",
            })

    return questions


async def query_external_sources(
    questions: list[dict],
    use_scibot: bool = True,
    use_multi_search: bool = True,
) -> list[dict]:
    """Send questions to external sources and collect answers.

    Returns [{question, source, answer, references}].
    """
    results = []

    for q in questions:
        question_text = q["question"]

        # Try Sci-Bot
        if use_scibot:
            try:
                from backend.agents.scibot_scraper import ask_scibot
                scibot_result = await ask_scibot(question_text)
                if scibot_result.get("answer"):
                    results.append({
                        **q,
                        "source": "scibot",
                        "answer": scibot_result["answer"],
                        "references": scibot_result.get("references", []),
                        "redirect_url": scibot_result.get("redirect_url"),
                    })
                    await asyncio.sleep(3)  # Be polite
                    continue  # Got an answer, move to next question
            except Exception as e:
                logger.debug(f"Sci-Bot failed for question: {e}")

        # Try multi-source search for paper discovery
        if use_multi_search:
            try:
                from backend.integrations.multi_source_search import multi_source_search
                search_result = await multi_source_search(
                    query=q["concept_name"],
                    limit_per_source=3,
                )
                if search_result["papers"]:
                    # Compose answer from paper abstracts
                    abstracts = [
                        f"- {p['title']} ({p.get('publication_year', '?')}): {p.get('abstract', '')[:200]}"
                        for p in search_result["papers"][:5]
                        if p.get("abstract")
                    ]
                    results.append({
                        **q,
                        "source": "multi_search",
                        "answer": "\n".join(abstracts) if abstracts else None,
                        "references": [
                            {"title": p["title"], "doi": p.get("doi"), "year": p.get("publication_year")}
                            for p in search_result["papers"][:5]
                        ],
                    })
            except Exception as e:
                logger.debug(f"Multi-search failed for question: {e}")

    return results


async def parse_and_store_findings(
    findings: list[dict],
    field_name: str,
    auto_apply_definitions: bool = False,
) -> dict:
    """Parse findings, evaluate critically, and store for admin review.

    Every finding goes through Critical Thinking before storage.
    NOTHING enters the graph without evaluation + admin approval.
    """
    client = get_client()
    stored = 0
    skipped = 0
    rejected = 0

    from backend.agents.critical_thinking import evaluate_and_log

    for finding in findings:
        concept_id = finding.get("concept_id")
        purpose = finding.get("purpose")
        answer = finding.get("answer")

        if not concept_id or not answer:
            skipped += 1
            continue

        # Critical evaluation
        assessment = await evaluate_and_log(
            claim_text=answer[:500],
            source=finding.get("source", "unknown"),
            concept_name=finding.get("concept_name"),
            field_name=field_name,
            references=finding.get("references"),
        )

        # Skip rejected findings
        if assessment.verdict == "reject":
            rejected += 1
            logger.info(f"Rejected finding for {finding['concept_name']}: {', '.join(assessment.reasons)}")
            continue

        # Map purpose to enrichment type
        enrichment_type = {
            "enrich_definition": "definition",
            "find_sources": "source",
            "assess_confidence": "confidence_update",
            "find_connections": "connection",
        }.get(purpose, "definition")

        # Priority based on concept importance + critical assessment
        priority = min(finding.get("paper_count", 0), 100)
        if assessment.contradicts:
            priority += 20  # contradictions are interesting

        # Store for admin review with critical assessment
        client.table("pending_enrichments").insert({
            "concept_id": concept_id,
            "concept_name": finding.get("concept_name", ""),
            "field": field_name,
            "enrichment_type": enrichment_type,
            "source": finding.get("source", "unknown"),
            "content": answer[:2000],
            "references": [
                *finding.get("references", [])[:10],
                {"_critical_assessment": {
                    "verdict": assessment.verdict,
                    "confidence": assessment.confidence,
                    "credibility": assessment.credibility_score,
                    "evidence_quality": assessment.evidence_quality,
                    "reasons": assessment.reasons,
                    "contradicts": assessment.contradicts,
                }},
            ],
            "question_asked": finding.get("question", ""),
            "status": "pending",
            "priority": priority,
        }).execute()
        stored += 1
        logger.info(
            f"Stored enrichment for {finding['concept_name']} "
            f"({assessment.verdict}, confidence={assessment.confidence:.2f})"
        )

    return {"stored_for_review": stored, "skipped": skipped, "rejected": rejected, "total": len(findings)}


async def run_enrichment_cycle(
    field_name: str,
    limit: int = 10,
    use_scibot: bool = True,
    use_multi_search: bool = True,
) -> dict:
    """Run one full enrichment cycle for a field.

    1. Find weak spots
    2. Generate questions
    3. Query external sources
    4. Parse and store findings
    """
    logger.info(f"Starting enrichment cycle for {field_name} (limit={limit})")

    # 1. Find weak spots
    weak_spots = await find_weak_spots(field_name, limit=limit)
    if not weak_spots:
        return {"status": "nothing_to_enrich", "field": field_name}

    logger.info(f"Found {len(weak_spots)} weak spots")

    # 2. Generate questions
    questions = generate_questions(weak_spots)
    logger.info(f"Generated {len(questions)} questions")

    # 3. Query external sources
    findings = await query_external_sources(
        questions,
        use_scibot=use_scibot,
        use_multi_search=use_multi_search,
    )
    logger.info(f"Got {len(findings)} findings")

    # 4. Parse and store for admin review
    result = await parse_and_store_findings(findings, field_name=field_name)

    return {
        "status": "complete",
        "field": field_name,
        "weak_spots_found": len(weak_spots),
        "questions_asked": len(questions),
        "findings_received": len(findings),
        **result,
    }


# CLI entry point
if __name__ == "__main__":
    import argparse
    import sys

    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Korczak Learning Agent")
    parser.add_argument("--field", default="Anthropology", help="Field to enrich")
    parser.add_argument("--limit", type=int, default=10, help="Max concepts to enrich")
    parser.add_argument("--no-scibot", action="store_true", help="Skip Sci-Bot queries")
    parser.add_argument("--no-search", action="store_true", help="Skip multi-source search")
    args = parser.parse_args()

    from dotenv import load_dotenv
    load_dotenv()

    result = asyncio.run(run_enrichment_cycle(
        field_name=args.field,
        limit=args.limit,
        use_scibot=not args.no_scibot,
        use_multi_search=not args.no_search,
    ))

    print(f"\n{'='*50}")
    print(f"Enrichment cycle complete:")
    print(f"  Field: {result.get('field')}")
    print(f"  Weak spots: {result.get('weak_spots_found', 0)}")
    print(f"  Questions asked: {result.get('questions_asked', 0)}")
    print(f"  Findings: {result.get('findings_received', 0)}")
    print(f"  Applied directly: {result.get('applied', 0)}")
    print(f"  Pending review: {result.get('pending', 0)}")
    print(f"{'='*50}")
