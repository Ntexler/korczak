"""Obsidian Integration API — bidirectional sync between Korczak and Obsidian vaults.

Export: concept/field → Obsidian Markdown
Import: Obsidian vault → analysis, gap detection, connection discovery
Insights: personalized findings from vault analysis
"""

import logging

from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from fastapi.responses import Response

from backend.core.obsidian_exporter import export_concept, export_field

logger = logging.getLogger(__name__)
router = APIRouter()


# ─── Export ───────────────────────────────────────────────────────────────────

@router.get("/export/concept/{concept_id}")
async def export_concept_markdown(concept_id: str):
    """Export a single concept as Obsidian-compatible Markdown."""
    try:
        result = await export_concept(concept_id)
        if not result:
            raise HTTPException(status_code=404, detail="Concept not found")

        return Response(
            content=result["content"],
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{result["filename"]}"',
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Export concept error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/export/concept/{concept_id}/json")
async def export_concept_json(concept_id: str):
    """Export a single concept as JSON (for programmatic access / Obsidian plugins)."""
    try:
        result = await export_concept(concept_id)
        if not result:
            raise HTTPException(status_code=404, detail="Concept not found")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Export concept JSON error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/export/field/{field_name}")
async def export_field_zip(field_name: str):
    """Export an entire field as a ZIP of Obsidian Markdown files."""
    try:
        zip_bytes = await export_field(field_name)
        if not zip_bytes:
            raise HTTPException(status_code=404, detail="No data found for this field")

        safe_name = field_name.replace(" ", "_").replace("&", "and")
        return Response(
            content=zip_bytes,
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="Korczak_{safe_name}.zip"',
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Export field error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ─── Import ──────────────────────────────────────────────────────────────────

@router.post("/import/vault")
async def import_vault(
    file: UploadFile = File(...),
    user_id: str = Query(default="mock-user"),
    field_name: str | None = Query(default=None),
):
    """Import an Obsidian vault (ZIP) for analysis.

    Parses all Markdown files, maps notes to Korczak concepts, detects gaps,
    finds hidden connections, and generates personalized insights.

    Does NOT modify global scores — only creates attention signals and insights.

    Returns the full analysis result including:
    - Note-to-concept mappings
    - Knowledge gaps
    - Hidden connections
    - Coverage statistics
    - Strengths
    """
    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Please upload a .zip file of your Obsidian vault")

    try:
        zip_bytes = await file.read()
        if len(zip_bytes) > 50 * 1024 * 1024:  # 50MB limit
            raise HTTPException(status_code=413, detail="Vault too large (max 50MB)")

        from backend.core.vault_parser import parse_vault_zip
        from backend.core.vault_analyzer import analyze_vault, save_analysis

        # Parse vault
        notes = parse_vault_zip(zip_bytes)
        if not notes:
            raise HTTPException(status_code=400, detail="No Markdown files found in vault")

        # Analyze
        result = await analyze_vault(notes, user_id=user_id, field_name=field_name)

        # Persist
        analysis_id = await save_analysis(result, user_id=user_id)

        # Build response
        return {
            "analysis_id": analysis_id,
            "stats": {
                "notes_parsed": result.stats.note_count,
                "total_links": result.stats.total_links,
                "total_tags": result.stats.total_tags,
                "total_words": result.stats.total_words,
                "avg_note_length": result.stats.avg_note_length,
            },
            "field_detected": result.field_name,
            "coverage_pct": result.coverage_pct,
            "mapped_concepts": sum(1 for m in result.mappings if m.concept_id),
            "unmapped_notes": sum(1 for m in result.mappings if not m.concept_id),
            "gaps": [
                {
                    "concept": g.concept_name,
                    "type": g.concept_type,
                    "paper_count": g.paper_count,
                    "why": g.why,
                }
                for g in result.gaps
            ],
            "hidden_connections": [
                {
                    "note_a": c.note_a,
                    "note_b": c.note_b,
                    "bridge_concept": c.connection_concept,
                    "relationship": c.relationship_type,
                    "explanation": c.explanation,
                }
                for c in result.connections
            ],
            "strengths": result.strengths,
            "mappings": [
                {
                    "note": m.note_title,
                    "concept": m.concept_name,
                    "confidence": m.confidence,
                    "method": m.match_method,
                }
                for m in result.mappings
                if m.concept_id  # only show successful mappings
            ],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Vault import error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ─── Insights ────────────────────────────────────────────────────────────────

@router.get("/insights")
async def get_insights(
    user_id: str = Query(default="mock-user"),
    include_dismissed: bool = False,
    limit: int = Query(default=20, le=50),
):
    """Get vault-derived insights for a user.

    Types: gap, misconception, hidden_connection, recommendation, strength, progress.
    """
    try:
        from backend.core.attention_engine import get_user_insights
        insights = await get_user_insights(
            user_id=user_id,
            include_dismissed=include_dismissed,
            limit=limit,
        )
        return {"insights": insights, "total": len(insights)}
    except Exception as e:
        logger.error(f"Get insights error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/insights/{insight_id}/dismiss")
async def dismiss_insight(insight_id: str):
    """Dismiss an insight (hide it from future results)."""
    try:
        from backend.core.attention_engine import dismiss_insight as _dismiss
        await _dismiss(insight_id)
        return {"status": "dismissed"}
    except Exception as e:
        logger.error(f"Dismiss insight error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analysis/history")
async def analysis_history(
    user_id: str = Query(default="mock-user"),
    limit: int = Query(default=5, le=20),
):
    """Get past vault analysis summaries for a user."""
    try:
        from backend.core.attention_engine import get_analysis_history
        analyses = await get_analysis_history(user_id=user_id, limit=limit)
        return {"analyses": analyses, "total": len(analyses)}
    except Exception as e:
        logger.error(f"Analysis history error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ─── Attention Signals ───────────────────────────────────────────────────────

@router.post("/signal")
async def create_attention_signal(
    user_id: str = Query(default="mock-user"),
    signal_type: str = Query(...),
    direction: str = Query(default="neutral"),
    target_type: str = Query(...),
    target_id: str | None = Query(default=None),
    target_name: str | None = Query(default=None),
    context: str | None = Query(default=None),
):
    """Create an attention signal manually (e.g., user flags a paper for review).

    signal_type: vault_note, saved_paper, rated, flagged
    direction: interest, skepticism, neutral
    target_type: concept, paper, claim, note
    """
    try:
        from backend.core.attention_engine import create_signal
        signal = await create_signal(
            user_id=user_id,
            signal_type=signal_type,
            direction=direction,
            target_type=target_type,
            target_id=target_id,
            target_name=target_name,
            context=context,
        )
        return signal
    except Exception as e:
        logger.error(f"Create signal error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/signals")
async def get_signals(
    user_id: str = Query(default="mock-user"),
    limit: int = Query(default=10, le=50),
):
    """Get pending attention signals for a user."""
    try:
        from backend.core.attention_engine import get_pending_signals
        signals = await get_pending_signals(user_id=user_id, limit=limit)
        return {"signals": signals, "total": len(signals)}
    except Exception as e:
        logger.error(f"Get signals error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
