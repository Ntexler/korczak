"""Chappie API — live missions with real-time SSE feed.

The ChappieLive frontend connects here: start a mission, then stream
real events as Chappie walks the literature. No more simulation.
"""

import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()

# In-memory mission broker: mission_id -> event queue
_missions: dict[str, asyncio.Queue] = {}
_MISSION_CAP = 20  # drop oldest queues beyond this


class MissionStart(BaseModel):
    field: str = "Anthropology"
    concept: str | None = None
    depth: int = 2
    max_papers: int = 10
    use_scibot: bool = True


@router.post("/mission/start")
async def start_mission(mission: MissionStart):
    """Launch a deep-dive mission. Returns mission_id for the SSE stream."""
    mission_id = uuid.uuid4().hex[:12]
    queue: asyncio.Queue = asyncio.Queue(maxsize=200)

    if len(_missions) >= _MISSION_CAP:
        oldest = next(iter(_missions))
        _missions.pop(oldest, None)
    _missions[mission_id] = queue

    async def emit(event: dict):
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            pass

    async def run():
        try:
            from backend.agents.deep_learner import deep_dive
            await deep_dive(
                field=mission.field,
                concept_name=mission.concept,
                depth=mission.depth,
                max_papers=mission.max_papers,
                emit=emit,
                use_scibot=mission.use_scibot,
            )
        except Exception as e:
            logger.error(f"Mission {mission_id} failed: {e}", exc_info=True)
            await emit({"type": "error", "message": str(e)})
        finally:
            await emit({"type": "_close", "message": "stream end"})

    asyncio.create_task(run())
    return {"mission_id": mission_id, "field": mission.field, "concept": mission.concept}


@router.get("/stream/{mission_id}")
async def stream_mission(mission_id: str):
    """SSE stream of a running mission's events."""
    queue = _missions.get(mission_id)
    if queue is None:
        raise HTTPException(status_code=404, detail="Mission not found or expired")

    async def event_source():
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=120)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                if event.get("type") == "_close":
                    yield f"data: {json.dumps({'type': 'close'})}\n\n"
                    break
                yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"
        finally:
            _missions.pop(mission_id, None)

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/journeys")
async def list_journeys(field: str | None = None, limit: int = Query(default=10, le=50)):
    """Chappie's past deep-dive journeys."""
    from backend.integrations.supabase_client import get_client
    client = get_client()
    query = client.table("chappie_journeys").select("*")
    if field:
        query = query.eq("field", field)
    result = query.order("created_at", desc=True).limit(limit).execute()
    return {"journeys": result.data or []}


@router.get("/consensus")
async def consensus_summary():
    """How much of Korczak's knowledge is agreed-upon base knowledge?"""
    from backend.agents.consensus import get_consensus_summary
    return await get_consensus_summary()


# ─── Paywall Missions (Sci-Bot interviews about locked papers) ──────────────

@router.post("/paywall/run")
async def run_paywall(
    field: str = Query(default="Anthropology"),
    papers: int = Query(default=5, le=15),
):
    """Send Chappie on a paywall shift: interview Sci-Bot about the
    most-cited locked papers in a field. Answers pass critical thinking
    and land in pending_enrichments."""
    from backend.agents.paywall_missions import run_paywall_shift
    return await run_paywall_shift(field=field, papers=papers)


class ManualAnswer(BaseModel):
    question: str
    answer: str
    concept_name: str | None = None
    field: str = "Anthropology"
    paper_title: str | None = None


@router.post("/paywall/manual-answer")
async def paste_scibot_answer(payload: ManualAnswer):
    """Sci-Bot is web-only — when Chappie couldn't get an answer via API,
    the interview logs a redirect URL. Ask Sci-Bot yourself, paste the
    answer here, and it flows through the EXACT same critical-thinking
    path as an automated answer."""
    from backend.agents.critical_thinking import evaluate_and_log
    from backend.integrations.supabase_client import get_client

    assessment = await evaluate_and_log(
        claim_text=payload.answer[:500],
        source="scibot",
        concept_name=payload.concept_name,
        field_name=payload.field,
        references=[{"title": payload.paper_title}] if payload.paper_title else None,
    )

    stored = False
    if assessment.verdict != "reject":
        client = get_client()
        client.table("pending_enrichments").insert({
            "concept_name": payload.concept_name or payload.paper_title or "manual scibot answer",
            "field": payload.field,
            "enrichment_type": "claim",
            "source": "scibot",
            "content": payload.answer[:2000],
            "references": [{"paper": payload.paper_title, "via": "manual_paste"}],
            "question_asked": payload.question[:400],
            "status": "pending",
            "priority": 40,
        }).execute()
        stored = True

    return {
        "verdict": assessment.verdict,
        "confidence": assessment.confidence,
        "reasons": assessment.reasons,
        "stored_for_review": stored,
    }


@router.post("/consensus/recompute")
async def recompute_consensus():
    """Recompute consensus tiers (run after seeding/enrichment)."""
    from backend.agents.consensus import compute_consensus
    return await compute_consensus()
