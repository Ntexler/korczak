"""Chappie's Deep Learner — real deep learning walks through the literature.

Not metadata collection. Chappie picks a concept, reads the papers behind it,
walks the citation trail hop by hop, asks Sci-Bot about locked papers he
can't read directly, and then SYNTHESIZES what he now understands:
what's agreed, what's contested, what's still open.

Every walk is recorded as a journey (chappie_journeys) and feeds:
- learning_log (what he learned)
- curiosity_queue (new questions the walk raised)
- pending_enrichments (proposed knowledge, admin-gated)
- consensus engine (recompute after walks)

Usage (also the nightly cron entry point):
  python -m backend.agents.deep_learner --field Anthropology --depth 2 --limit 3
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

OPENALEX_BASE = "https://api.openalex.org"

# Type for SSE event emitters: async callback receiving a dict
Emitter = "callable | None"


async def _emit(emit, event_type: str, message: str, **detail):
    """Push an event to the live feed (no-op if no emitter)."""
    if emit:
        try:
            await emit({
                "type": event_type,
                "message": message,
                "time": datetime.now(timezone.utc).isoformat(),
                **detail,
            })
        except Exception:
            pass
    logger.info(f"[chappie:{event_type}] {message}")


async def _fetch_work(openalex_id: str) -> dict | None:
    """Fetch a single work's metadata from OpenAlex (free)."""
    params = {"select": "id,title,publication_year,cited_by_count,doi,"
                        "abstract_inverted_index,referenced_works"}
    email = os.getenv("OPENALEX_EMAIL")
    if email:
        params["mailto"] = email
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{OPENALEX_BASE}/works/{openalex_id}", params=params, timeout=15)
            if resp.status_code == 200:
                return resp.json()
    except Exception:
        pass
    return None


def _abstract_of(work: dict) -> str:
    from backend.pipeline.seed_optimized import reconstruct_abstract
    return reconstruct_abstract(work.get("abstract_inverted_index"))


async def deep_dive(
    field: str,
    concept_name: str | None = None,
    depth: int = 2,
    max_papers: int = 10,
    emit=None,
    use_scibot: bool = True,
) -> dict:
    """One deep learning walk. Returns the journey record."""
    from backend.integrations.supabase_client import get_client
    client = get_client()

    # ── 1. Pick a target ──
    if not concept_name:
        from backend.agents.learning_agent import find_weak_spots
        weak = await find_weak_spots(field, limit=1)
        if not weak:
            await _emit(emit, "done", f"Nothing needs a deep dive in {field} right now")
            return {"status": "nothing_to_learn"}
        concept_name = weak[0]["concept_name"]
        concept_id = weak[0]["concept_id"]
    else:
        rows = client.table("concepts").select("id").ilike("name", f"%{concept_name}%").limit(1).execute()
        concept_id = rows.data[0]["id"] if rows.data else None

    await _emit(emit, "started", f"Deep dive: {concept_name}", concept=concept_name, field=field)

    # Create journey record
    journey = client.table("chappie_journeys").insert({
        "field": field,
        "start_concept": concept_name,
        "status": "walking",
    }).execute()
    journey_id = journey.data[0]["id"] if journey.data else None

    notes: list[str] = []           # reading notes for synthesis
    path: list[dict] = []           # citation trail
    sources_consulted: list[dict] = []
    papers_read = 0

    # ── 2. Seed papers from our graph ──
    seed_papers: list[dict] = []
    if concept_id:
        pc = client.table("paper_concepts").select("paper_id, relevance").eq(
            "concept_id", concept_id
        ).order("relevance", desc=True).limit(4).execute()
        pids = [r["paper_id"] for r in (pc.data or [])]
        for i in range(0, len(pids), 40):
            rows = client.table("papers").select(
                "id, openalex_id, title, publication_year, abstract, cited_by_count"
            ).in_("id", pids[i:i + 40]).execute()
            seed_papers.extend(rows.data or [])

    # ── 3. Read seeds + walk citations ──
    frontier = []  # openalex ids to walk next hop
    for p in seed_papers[:4]:
        title = p.get("title", "")
        await _emit(emit, "reading", f"Reading: {title[:70]}", hop=0)
        snippet = (p.get("abstract") or "")[:400]

        if snippet:
            notes.append(f"[{title} ({p.get('publication_year')})] {snippet}")
            papers_read += 1
        elif use_scibot and title:
            # Locked/missing abstract — ask Sci-Bot (his window into full text)
            await _emit(emit, "scibot", f"Paper is locked — asking Sci-Bot about: {title[:60]}")
            try:
                from backend.agents.scibot_scraper import ask_scibot
                sb = await ask_scibot(f"What are the key findings and arguments of the paper '{title}' ({p.get('publication_year')})?")
                sources_consulted.append({"source": "scibot", "query": title[:100],
                                          "result_summary": (sb.get("answer") or "no answer — redirect only")[:200]})
                if sb.get("answer"):
                    notes.append(f"[{title} — via Sci-Bot full-text] {sb['answer'][:400]}")
                    papers_read += 1
            except Exception as e:
                logger.debug(f"Sci-Bot ask failed: {e}")

        path.append({"paper": title[:100], "via": "seed", "hop": 0})
        if p.get("openalex_id"):
            frontier.append(p["openalex_id"])

    # Citation walking: hop along referenced_works
    for hop in range(1, depth + 1):
        if papers_read >= max_papers or not frontier:
            break
        next_frontier = []
        for oa_id in frontier[:3]:
            work = await _fetch_work(oa_id)
            if not work:
                continue
            refs = [r.split("/")[-1] for r in (work.get("referenced_works") or [])][:8]
            # Read the most cited references this hop
            for ref_id in refs[:3]:
                if papers_read >= max_papers:
                    break
                ref = await _fetch_work(ref_id)
                if not ref:
                    continue
                title = ref.get("title", "")
                abstract = _abstract_of(ref)
                await _emit(emit, "walking", f"Hop {hop}: following citation → {title[:60]}", hop=hop)
                if abstract:
                    notes.append(f"[{title} ({ref.get('publication_year')}), hop {hop}] {abstract[:350]}")
                    papers_read += 1
                path.append({"paper": title[:100], "via": "citation", "hop": hop})
                next_frontier.append(ref_id)
                await asyncio.sleep(0.15)  # polite to OpenAlex
        frontier = next_frontier

    # ── 4. Synthesize understanding ──
    synthesis_result = {"synthesis": "", "consensus_points": [], "contested_points": [], "open_questions": []}
    if notes:
        await _emit(emit, "thinking", f"Read {papers_read} papers — synthesizing understanding...")
        try:
            from backend.config import settings
            from backend.integrations.claude_client import _call_claude
            from backend.agents.persona import CHAPPIE_IDENTITY

            prompt = (
                f"{CHAPPIE_IDENTITY}\n\n"
                f"You just finished a deep reading walk on '{concept_name}' in {field}. "
                f"Your reading notes ({papers_read} papers, including citation trail):\n\n"
                + "\n\n".join(notes[:12])
                + "\n\nSynthesize what you NOW understand. Return JSON only:\n"
                '{"synthesis": "2-4 sentences: what you understand now",\n'
                ' "consensus_points": ["things the sources AGREE on"],\n'
                ' "contested_points": ["things sources DISAGREE on"],\n'
                ' "open_questions": ["what you still want to find out"]}'
            )
            resp = await _call_claude(prompt, model=settings.haiku_model, max_tokens=800, temperature=0.3)
            text = resp.text
            if "```" in text:
                text = text.split("```")[1].removeprefix("json").strip()
            synthesis_result = json.loads(text)
        except Exception as e:
            logger.warning(f"Synthesis failed: {e}")
            synthesis_result["synthesis"] = f"Read {papers_read} papers on {concept_name}; synthesis unavailable."

    # ── 5. Feed what he learned back into the system ──
    try:
        from backend.agents.consciousness import log_learning, add_curiosity

        if synthesis_result.get("synthesis"):
            await log_learning(
                entry_type="deepened",
                summary=f"Deep dive on {concept_name}: {synthesis_result['synthesis'][:200]}",
                concept_name=concept_name, concept_id=concept_id, field=field,
                source="deep_dive", confidence=0.6,
                detail=json.dumps(synthesis_result, ensure_ascii=False)[:1500],
            )
        for point in synthesis_result.get("contested_points", [])[:3]:
            await log_learning(
                entry_type="contradicted",
                summary=f"Sources disagree on {concept_name}: {point[:180]}",
                concept_name=concept_name, field=field, source="deep_dive", confidence=0.5,
            )
            await _emit(emit, "contradiction", f"Found disagreement: {point[:100]}")
        for q in synthesis_result.get("open_questions", [])[:3]:
            await add_curiosity(question=q, trigger=f"deep dive on {concept_name}",
                                field=field, concept_name=concept_name, priority=5)

        # Propose the synthesis as an enrichment (admin-gated, critically evaluated)
        if synthesis_result.get("synthesis") and concept_id:
            from backend.agents.critical_thinking import evaluate_and_log
            assessment = await evaluate_and_log(
                claim_text=synthesis_result["synthesis"],
                source="multi_search",  # academic-derived synthesis
                concept_name=concept_name, field_name=field,
                references=[{"title": p["paper"], "hop": p["hop"]} for p in path[:8]],
            )
            if assessment.verdict != "reject":
                client.table("pending_enrichments").insert({
                    "concept_id": concept_id,
                    "concept_name": concept_name,
                    "field": field,
                    "enrichment_type": "definition",
                    "source": "chappie_deep_dive",
                    "content": synthesis_result["synthesis"][:2000],
                    "references": [{"title": p["paper"], "hop": p["hop"]} for p in path[:10]],
                    "question_asked": f"Deep dive walk: {concept_name}",
                    "status": "pending",
                    "priority": 30,
                }).execute()
    except Exception as e:
        logger.warning(f"Feedback loop failed: {e}")

    # ── 6. Close the journey ──
    if journey_id:
        client.table("chappie_journeys").update({
            "path": path,
            "sources_consulted": sources_consulted,
            "synthesis": synthesis_result.get("synthesis", ""),
            "consensus_found": synthesis_result.get("consensus_points", [])[:10],
            "contested_found": synthesis_result.get("contested_points", [])[:10],
            "open_questions": synthesis_result.get("open_questions", [])[:10],
            "hops": max((p["hop"] for p in path), default=0),
            "papers_read": papers_read,
            "status": "complete",
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", journey_id).execute()

    await _emit(emit, "done",
                f"Deep dive complete: {papers_read} papers, "
                f"{len(synthesis_result.get('contested_points', []))} disagreements found",
                synthesis=synthesis_result.get("synthesis", ""))

    return {
        "journey_id": journey_id,
        "concept": concept_name,
        "papers_read": papers_read,
        "hops": max((p["hop"] for p in path), default=0),
        **synthesis_result,
    }


async def nightly_run(field: str, dives: int = 3, depth: int = 2) -> list[dict]:
    """Chappie's autonomous night shift: several deep dives + consensus refresh."""
    results = []
    for i in range(dives):
        logger.info(f"Night dive {i+1}/{dives} in {field}")
        result = await deep_dive(field=field, depth=depth)
        results.append(result)
        if result.get("status") == "nothing_to_learn":
            break
        await asyncio.sleep(2)

    # Recompute consensus after learning
    try:
        from backend.agents.consensus import compute_consensus
        consensus = await compute_consensus()
        logger.info(f"Consensus refreshed: {consensus}")
    except Exception as e:
        logger.warning(f"Consensus refresh failed: {e}")

    # Morning reflection
    try:
        from backend.agents.consciousness import generate_reflection
        await generate_reflection(reflection_type="daily", field=field)
    except Exception as e:
        logger.warning(f"Reflection failed: {e}")

    return results


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    parser = argparse.ArgumentParser(description="Chappie deep learning walks")
    parser.add_argument("--field", default="Anthropology")
    parser.add_argument("--concept", default=None, help="Specific concept (default: auto-pick weakest)")
    parser.add_argument("--depth", type=int, default=2, help="Citation hops")
    parser.add_argument("--limit", type=int, default=3, help="Dives per run (nightly mode)")
    parser.add_argument("--no-scibot", action="store_true")
    args = parser.parse_args()

    if args.concept:
        result = asyncio.run(deep_dive(
            field=args.field, concept_name=args.concept,
            depth=args.depth, use_scibot=not args.no_scibot,
        ))
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    else:
        results = asyncio.run(nightly_run(args.field, dives=args.limit, depth=args.depth))
        print(f"\nNight shift done: {len(results)} dives")
        for r in results:
            print(f"  - {r.get('concept')}: {r.get('papers_read', 0)} papers, "
                  f"{len(r.get('contested_points', []))} disagreements")
