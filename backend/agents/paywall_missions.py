"""Paywall Missions — Chappie interviews Sci-Bot about locked papers.

The canonical, most-cited papers are often exactly the ones behind
paywalls. Chappie can't read them — but Sci-Bot (88M full-text papers)
can. This module runs structured INTERVIEWS, not single questions:

Per locked paper, three targeted questions:
  1. Key findings + the evidence behind them
  2. Methodology and its limitations
  3. How the paper relates to the concept it's linked to in our graph

Every answer passes critical thinking (source='scibot', credibility 0.7,
rejection-history penalties apply) before landing in pending_enrichments.
Every interview is recorded as a chappie_journey.

Honest fallback: Sci-Bot has no confirmed API. When it doesn't answer,
the interview is logged as 'pending' WITH the redirect URL — you can ask
manually and paste the answer back via the admin endpoint, and it flows
through the exact same critical-thinking path.

Usage:
  python -m backend.agents.paywall_missions --field Anthropology --papers 5
"""

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


async def find_paywalled_targets(field: str, limit: int = 10) -> list[dict]:
    """Locked, important papers: not open-access (or unknown), most-cited first.

    Priority: canonical papers — high citations, thin local knowledge
    (short/missing abstract means we know least about what matters most).
    """
    from backend.integrations.supabase_client import get_client
    from backend.core.fields import get_field_paper_ids
    client = get_client()

    ids = get_field_paper_ids(client, field)
    if not ids:
        return []

    papers = []
    for i in range(0, min(len(ids), 600), 40):
        rows = client.table("papers").select(
            "id, title, publication_year, doi, cited_by_count, abstract, open_access"
        ).in_("id", ids[i:i + 40]).execute()
        papers.extend(rows.data or [])

    def locked_score(p: dict) -> float:
        # open_access True → not a target; None/False → candidate
        if p.get("open_access") is True:
            return -1
        cited = p.get("cited_by_count", 0)
        thin = 1.5 if len(p.get("abstract") or "") < 200 else 1.0
        return cited * thin

    targets = [p for p in papers if locked_score(p) > 0]
    targets.sort(key=locked_score, reverse=True)
    return targets[:limit]


def _interview_questions(paper: dict, concept_name: str | None) -> list[dict]:
    title = paper.get("title", "")
    year = paper.get("publication_year", "")
    qs = [
        {"purpose": "findings",
         "q": f"What are the key findings of '{title}' ({year}), and what evidence supports each finding?"},
        {"purpose": "methodology",
         "q": f"What methodology does '{title}' ({year}) use, and what are its main limitations?"},
    ]
    if concept_name:
        qs.append({"purpose": "relation",
                   "q": f"How does '{title}' ({year}) contribute to or challenge the concept of {concept_name}?"})
    return qs


async def interview_paper(paper: dict, field: str) -> dict:
    """One structured Sci-Bot interview about a locked paper."""
    from backend.integrations.supabase_client import get_client
    from backend.agents.scibot_scraper import ask_scibot, _make_url
    client = get_client()

    # Which concept is this paper about (for the relation question)?
    concept_name, concept_id = None, None
    try:
        pc = client.table("paper_concepts").select("concept_id").eq(
            "paper_id", paper["id"]
        ).order("relevance", desc=True).limit(1).execute()
        if pc.data:
            concept_id = pc.data[0]["concept_id"]
            c = client.table("concepts").select("name").eq("id", concept_id).execute()
            concept_name = c.data[0]["name"] if c.data else None
    except Exception:
        pass

    questions = _interview_questions(paper, concept_name)
    answers = []
    got_any = False

    for q in questions:
        result = await ask_scibot(q["q"])
        answered = bool(result.get("answer"))
        got_any = got_any or answered
        answers.append({
            "purpose": q["purpose"],
            "question": q["q"],
            "answer": result.get("answer"),
            "references": result.get("references", []),
            "redirect_url": result.get("redirect_url"),
            "status": "answered" if answered else "pending_manual",
        })
        await asyncio.sleep(3)  # polite

    # Record the interview as a journey
    journey = client.table("chappie_journeys").insert({
        "field": field,
        "start_concept": concept_name or paper.get("title", "")[:80],
        "sources_consulted": [
            {"source": "scibot", "query": a["question"][:120],
             "result_summary": (a["answer"] or f"no answer — ask manually: {a['redirect_url']}")[:200]}
            for a in answers
        ],
        "papers_read": 1 if got_any else 0,
        "status": "complete" if got_any else "aborted",
        "synthesis": "",
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }).execute()
    journey_id = journey.data[0]["id"] if journey.data else None

    # Feed answered questions through critical thinking → pending_enrichments
    stored = 0
    for a in answers:
        if not a["answer"]:
            continue
        try:
            from backend.agents.critical_thinking import evaluate_and_log
            assessment = await evaluate_and_log(
                claim_text=a["answer"][:500],
                source="scibot",
                concept_name=concept_name,
                field_name=field,
                references=a.get("references"),
            )
            if assessment.verdict != "reject":
                client.table("pending_enrichments").insert({
                    "concept_id": concept_id,
                    "concept_name": concept_name or paper.get("title", "")[:100],
                    "field": field,
                    "enrichment_type": "claim" if a["purpose"] == "findings" else "definition",
                    "source": "scibot",
                    "content": a["answer"][:2000],
                    "references": (a.get("references") or [])[:8] + [
                        {"paper": paper.get("title"), "doi": paper.get("doi"),
                         "interview_purpose": a["purpose"], "journey_id": journey_id}
                    ],
                    "question_asked": a["question"][:400],
                    "status": "pending",
                    "priority": min(paper.get("cited_by_count", 0) // 10, 90),
                }).execute()
                stored += 1
        except Exception as e:
            logger.warning(f"Interview answer processing failed: {e}")

    return {
        "paper": paper.get("title", "")[:80],
        "cited_by": paper.get("cited_by_count", 0),
        "questions": len(questions),
        "answered": sum(1 for a in answers if a["answer"]),
        "stored_for_review": stored,
        "manual_urls": [a["redirect_url"] for a in answers if not a["answer"]],
        "journey_id": journey_id,
    }


async def run_paywall_shift(field: str, papers: int = 5) -> dict:
    """Chappie's paywall shift: interview Sci-Bot about the most important
    locked papers in a field. Cron-able."""
    logger.info(f"Paywall shift: {field}, up to {papers} papers")
    targets = await find_paywalled_targets(field, limit=papers)
    if not targets:
        return {"status": "no_paywalled_targets", "field": field}

    results = []
    for p in targets:
        logger.info(f"  Interviewing Sci-Bot about: {p.get('title', '')[:60]} "
                    f"({p.get('cited_by_count', 0)} citations)")
        results.append(await interview_paper(p, field))

    answered = sum(r["answered"] for r in results)
    try:
        from backend.agents.consciousness import log_learning
        await log_learning(
            entry_type="from_expert" if answered else "discovered",
            summary=f"Paywall shift in {field}: interviewed Sci-Bot about "
                    f"{len(results)} locked papers, got {answered} answers",
            field=field, source="scibot", confidence=0.6,
        )
    except Exception:
        pass

    return {
        "status": "complete",
        "field": field,
        "papers_interviewed": len(results),
        "answers_received": answered,
        "stored_for_review": sum(r["stored_for_review"] for r in results),
        "interviews": results,
    }


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    parser = argparse.ArgumentParser(description="Chappie's paywall shift via Sci-Bot")
    parser.add_argument("--field", default="Anthropology")
    parser.add_argument("--papers", type=int, default=5)
    args = parser.parse_args()

    result = asyncio.run(run_paywall_shift(args.field, args.papers))
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
