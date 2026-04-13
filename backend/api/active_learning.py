"""Active Learning API — contradiction detection, depth slider, quiz mode."""

import logging

from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/evidence/{concept_id}")
async def claim_evidence_map(concept_id: str):
    """Get claims for a concept with inline support/contradiction indicators.

    Each claim includes:
    - support_count / contradict_count
    - status: well_supported, debated, challenged, single_source
    - contradicting claim texts
    """
    try:
        from backend.core.active_learning import get_claim_evidence_map
        claims = await get_claim_evidence_map(concept_id)
        return {"concept_id": concept_id, "claims": claims, "total": len(claims)}
    except Exception as e:
        logger.error(f"Evidence map error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/explain/{concept_id}")
async def explain_at_depth(
    concept_id: str,
    depth: int = Query(default=2, ge=1, le=5),
    locale: str = "en",
    user_context: str | None = None,
):
    """Generate an explanation at a specific depth level.

    depth: 1=high school, 2=undergrad, 3=advanced, 4=graduate, 5=expert
    """
    try:
        from backend.core.active_learning import explain_at_depth as _explain
        result = await _explain(
            concept_id=concept_id,
            depth=depth,
            locale=locale,
            user_context=user_context,
        )
        if not result:
            raise HTTPException(status_code=404, detail="Concept not found")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Depth explain error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/depth-levels")
async def get_depth_levels():
    """Get available depth levels with labels."""
    from backend.core.active_learning import DEPTH_LEVELS
    return {
        "levels": [
            {"depth": k, "label": v["label"], "label_he": v["label_he"]}
            for k, v in DEPTH_LEVELS.items()
        ]
    }


@router.get("/quiz")
async def generate_quiz(
    field_name: str | None = None,
    concept_ids: str | None = Query(default=None, description="Comma-separated concept IDs"),
    count: int = Query(default=5, ge=1, le=20),
    locale: str = "en",
):
    """Generate quiz questions from the knowledge graph.

    Either field_name or concept_ids must be provided.
    """
    try:
        from backend.core.active_learning import generate_quiz as _quiz

        ids = None
        if concept_ids:
            ids = [c.strip() for c in concept_ids.split(",") if c.strip()]

        if not ids and not field_name:
            raise HTTPException(status_code=400, detail="Provide field_name or concept_ids")

        questions = await _quiz(
            concept_ids=ids,
            field_name=field_name,
            question_count=count,
            locale=locale,
        )
        return {"questions": questions, "total": len(questions)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Quiz generation error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
