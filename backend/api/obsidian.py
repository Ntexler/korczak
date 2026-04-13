"""Obsidian Integration API — export Korczak knowledge graph to Obsidian vault format."""

import logging

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from backend.core.obsidian_exporter import export_concept, export_field

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/export/concept/{concept_id}")
async def export_concept_markdown(concept_id: str):
    """Export a single concept as Obsidian-compatible Markdown.

    Returns the Markdown content as a downloadable .md file.
    """
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
    """Export a single concept as JSON (for programmatic access / Obsidian plugins).

    Returns {filename, content} where content is the Markdown string.
    """
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
    """Export an entire field as a ZIP of Obsidian Markdown files.

    The ZIP contains:
      Korczak — {field}/
        Concepts/{name}.md
        Papers/{author year — title}.md
        _Index.md
    """
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
