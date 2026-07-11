"""Media-as-evidence API.

- GET  /api/media/concepts/{id}          → stored media for a concept (fast, no LLM)
- POST /api/media/concepts/{id}/discover → on-demand: search + interpret + store
- POST /api/media/contribute             → a lecturer/researcher points at a clip
                                            (pasted URL) that illustrates a claim

On-demand discovery and contribution are how Korczak shows a founding Bush
interview EMBEDDED next to a 9/11 claim — with its meaning, not a link out.
"""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.integrations.supabase_client import get_client

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/concepts/{concept_id}")
async def get_concept_media(concept_id: str, limit: int = 12):
    """Stored media evidence for a concept, best-relevance first. No LLM cost."""
    client = get_client()
    try:
        res = (client.table("media_evidence")
               .select("*").eq("concept_id", concept_id)
               .order("relevance", desc=True).limit(min(limit, 40)).execute())
        return {"concept_id": concept_id, "media": res.data or []}
    except Exception as e:
        logger.warning(f"get_concept_media failed: {e}")
        return {"concept_id": concept_id, "media": []}


@router.post("/concepts/{concept_id}/discover")
async def discover_media(concept_id: str, limit: int = 4, sources: list[str] | None = None):
    """On-demand: find + interpret + store media that reinforces this concept."""
    from backend.integrations.media_sources import search_media
    from backend.agents.media_interpreter import assess_and_store

    client = get_client()
    concept = _load_concept(client, concept_id)
    if not concept:
        raise HTTPException(status_code=404, detail="concept not found")

    query = concept["name"]
    claim = concept.get("definition") or concept["name"]

    records = await search_media(query, limit_per_source=limit, sources=sources)
    stored = []
    for rec in records[: limit * 2]:
        row = await assess_and_store(
            client, rec, concept_id, concept["name"], claim, brought_by="on_demand")
        if row:
            stored.append(row)
    return {"concept_id": concept_id, "found": len(records), "stored": len(stored), "media": stored}


class ContributeIn(BaseModel):
    concept_id: str
    url: str                      # a YouTube / archive.org URL
    note: str | None = None       # why this clip matters (optional; sharpens the reading)
    contributed_by: str | None = None


@router.post("/contribute")
async def contribute_media(body: ContributeIn):
    """A lecturer/researcher points Korczak at a clip that illustrates a claim.

    This is how the platform GROWS through its users — the contributed clip
    goes through the exact same interpretation + grounding pipeline.
    """
    from backend.integrations.media_sources import youtube_from_url, search_archive_media
    from backend.agents.media_interpreter import assess_and_store

    client = get_client()
    concept = _load_concept(client, body.concept_id)
    if not concept:
        raise HTTPException(status_code=404, detail="concept not found")

    record = None
    if "youtube.com" in body.url or "youtu.be" in body.url:
        record = await youtube_from_url(body.url)
    elif "archive.org" in body.url:
        ident = body.url.rstrip("/").split("/")[-1]
        hits = await search_archive_media(ident, limit=1)
        record = hits[0] if hits else None
    if not record:
        raise HTTPException(status_code=400, detail="unsupported or unrecognized media URL")

    claim = body.note or concept.get("definition") or concept["name"]
    row = await assess_and_store(
        client, record, body.concept_id, concept["name"], claim,
        brought_by="contributor", contributed_by=body.contributed_by)
    if not row:
        raise HTTPException(status_code=500, detail="could not store contributed media")
    return {"stored": row}


def _load_concept(client, concept_id: str) -> dict | None:
    try:
        res = (client.table("concepts")
               .select("id,name,definition,type")
               .eq("id", concept_id).limit(1).execute())
        return (res.data or [None])[0]
    except Exception as e:
        logger.warning(f"concept load failed: {e}")
        return None
