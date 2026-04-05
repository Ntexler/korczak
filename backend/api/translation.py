"""Translation API — translate papers across languages."""

import logging

from fastapi import APIRouter, HTTPException, Query

from backend.core.paper_translator import (
    translate_paper,
    get_cached_translation,
    flag_translation,
    get_available_languages,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/translate")
async def translate(
    paper_id: str = Query(...),
    target_lang: str = Query(default="en"),
):
    """Translate a paper to the target language. Uses cache if available."""
    try:
        result = await translate_paper(paper_id, target_lang)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Translation error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{paper_id}")
async def get_translation(
    paper_id: str,
    lang: str = Query(default="en"),
):
    """Get cached translation for a paper."""
    try:
        result = await get_cached_translation(paper_id, lang)
        if not result:
            raise HTTPException(status_code=404, detail="Translation not found. Use POST /translate to create one.")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get translation error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{translation_id}/flag")
async def flag_bad_translation(translation_id: str):
    """Flag a translation as poor quality."""
    try:
        return await flag_translation(translation_id)
    except Exception as e:
        logger.error(f"Flag translation error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/languages/supported")
async def supported_languages():
    """Get list of supported languages."""
    try:
        return await get_available_languages()
    except Exception as e:
        logger.error(f"Languages error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
