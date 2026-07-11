"""Echo API — a moment's textual wake, surfaced per concept.

- GET  /api/echo/concepts/{id}          → stored echoes (fast, no external calls)
- POST /api/echo/concepts/{id}/analyze  → run the echo pipeline for this concept

The echoes point at WHICH moment mattered and WHEN, and carry the analysis
the culture gave it — so the UI can say "here's why this moment mattered"
and, later, aim visual analysis at exactly the right timestamp.
"""

import logging

from fastapi import APIRouter, HTTPException

from backend.integrations.supabase_client import get_client

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/concepts/{concept_id}")
async def get_echoes(concept_id: str):
    """Stored echoes for a concept, strongest first. No external cost."""
    client = get_client()
    try:
        res = (client.table("concept_echoes").select("*")
               .eq("concept_id", concept_id)
               .order("signal_strength", desc=True).limit(60).execute())
        return {"concept_id": concept_id, "echoes": res.data or []}
    except Exception as e:
        logger.warning(f"get_echoes failed: {e}")
        return {"concept_id": concept_id, "echoes": []}


@router.post("/concepts/{concept_id}/analyze")
async def analyze_echoes(concept_id: str):
    """Read the textual wake of this concept: peak moments + the analysis
    they provoked. Runs live external queries — may take ~15-30s."""
    from backend.agents.echo_pipeline import analyze_concept

    client = get_client()
    res = client.table("concepts").select("id,name,type").eq("id", concept_id).limit(1).execute()
    concept = (res.data or [None])[0]
    if not concept:
        raise HTTPException(status_code=404, detail="concept not found")
    return await analyze_concept(client, concept)
