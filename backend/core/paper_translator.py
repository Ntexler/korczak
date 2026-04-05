"""Paper Translator — translate foreign-language papers using Claude API."""

import logging
import json

from backend.integrations.supabase_client import get_client
from backend.integrations.claude_client import _call_claude

logger = logging.getLogger(__name__)

# Languages we can detect and translate
SUPPORTED_LANGUAGES = {
    "en": "English",
    "he": "Hebrew",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "pt": "Portuguese",
    "ru": "Russian",
    "ar": "Arabic",
    "it": "Italian",
    "nl": "Dutch",
    "pl": "Polish",
    "tr": "Turkish",
    "sv": "Swedish",
    "da": "Danish",
    "no": "Norwegian",
    "fi": "Finnish",
    "cs": "Czech",
    "el": "Greek",
    "hi": "Hindi",
    "th": "Thai",
    "vi": "Vietnamese",
    "id": "Indonesian",
}


def detect_language(text: str) -> str:
    """Simple language detection based on character ranges and common patterns.
    Returns ISO 639-1 code."""
    if not text:
        return "en"

    # Check for script-based detection
    for char in text[:200]:
        code = ord(char)
        if 0x4E00 <= code <= 0x9FFF:
            return "zh"
        if 0x3040 <= code <= 0x309F or 0x30A0 <= code <= 0x30FF:
            return "ja"
        if 0xAC00 <= code <= 0xD7AF:
            return "ko"
        if 0x0590 <= code <= 0x05FF:
            return "he"
        if 0x0600 <= code <= 0x06FF:
            return "ar"
        if 0x0E00 <= code <= 0x0E7F:
            return "th"
        if 0x0900 <= code <= 0x097F:
            return "hi"
        if 0x0400 <= code <= 0x04FF:
            return "ru"
        if 0x0370 <= code <= 0x03FF:
            return "el"

    # Default to English for Latin scripts
    return "en"


async def get_cached_translation(paper_id: str, target_lang: str) -> dict | None:
    """Check if a translation already exists in cache."""
    client = get_client()
    result = (
        client.table("paper_translations")
        .select("*")
        .eq("paper_id", paper_id)
        .eq("target_language", target_lang)
        .execute()
    )
    return result.data[0] if result.data else None


async def translate_paper(paper_id: str, target_lang: str) -> dict:
    """Translate a paper's title and abstract to the target language.
    Uses cache if available, otherwise translates via Claude."""

    # Check cache first
    cached = await get_cached_translation(paper_id, target_lang)
    if cached:
        return cached

    # Get the paper
    client = get_client()
    paper_result = (
        client.table("papers")
        .select("id, title, abstract, language")
        .eq("id", paper_id)
        .execute()
    )
    if not paper_result.data:
        raise ValueError(f"Paper {paper_id} not found")

    paper = paper_result.data[0]
    source_lang = paper.get("language") or detect_language(paper.get("abstract") or paper.get("title", ""))

    # Don't translate if already in target language
    if source_lang == target_lang:
        return {
            "paper_id": paper_id,
            "source_language": source_lang,
            "target_language": target_lang,
            "translated_title": paper["title"],
            "translated_abstract": paper.get("abstract"),
            "already_in_target": True,
        }

    source_name = SUPPORTED_LANGUAGES.get(source_lang, source_lang)
    target_name = SUPPORTED_LANGUAGES.get(target_lang, target_lang)

    # Translate via Claude
    prompt = f"""Translate the following academic paper content from {source_name} to {target_name}.

IMPORTANT RULES:
1. Preserve all technical/academic terminology accurately
2. Keep proper nouns (author names, place names, institution names) unchanged
3. Maintain the academic tone and register
4. If a technical term has no standard translation in {target_name}, keep the original term in parentheses
5. Return ONLY valid JSON, no other text

Input:
- Title: {paper['title']}
- Abstract: {paper.get('abstract', 'N/A')}

Return JSON:
{{"translated_title": "...", "translated_abstract": "...", "quality_notes": "any concerns about translation quality"}}"""

    try:
        text = await _call_claude(prompt, max_tokens=2000)
        text = text.strip()
        # Handle potential markdown code blocks
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        translation = json.loads(text)

        # Cache the translation
        cache_data = {
            "paper_id": paper_id,
            "source_language": source_lang,
            "target_language": target_lang,
            "translated_title": translation.get("translated_title"),
            "translated_abstract": translation.get("translated_abstract"),
            "translator_model": "claude-sonnet-4-6-20250514",
            "quality_score": 0.85,  # Default quality score
        }

        result = client.table("paper_translations").upsert(
            cache_data,
            on_conflict="paper_id,target_language",
        ).execute()

        return result.data[0] if result.data else cache_data

    except json.JSONDecodeError:
        logger.error(f"Failed to parse translation response for paper {paper_id}")
        raise ValueError("Translation response was not valid JSON")
    except Exception as e:
        logger.error(f"Translation error for paper {paper_id}: {e}", exc_info=True)
        raise


async def flag_translation(translation_id: str) -> dict:
    """Flag a translation as poor quality."""
    client = get_client()
    result = (
        client.table("paper_translations")
        .update({"flagged": True})
        .eq("id", translation_id)
        .execute()
    )
    return result.data[0] if result.data else {"status": "flagged"}


async def get_available_languages() -> dict:
    """Return supported languages."""
    return {
        "languages": [
            {"code": code, "name": name}
            for code, name in SUPPORTED_LANGUAGES.items()
        ],
        "count": len(SUPPORTED_LANGUAGES),
    }
