"""Claude API client — abstraction layer for LLM calls."""

import json

import httpx

from backend.config import settings

API_URL = "https://api.anthropic.com/v1/messages"


async def analyze_paper(title: str, authors: str, year: int, abstract: str) -> dict:
    """Analyze a paper using the Phase 0.5 prompt."""
    from backend.prompts.paper_analysis import ANALYSIS_PROMPT

    prompt = ANALYSIS_PROMPT.format(
        title=title, authors=authors, year=year, abstract=abstract,
    )
    response = await _call_claude(prompt, model=settings.analysis_model, max_tokens=2000)
    return _parse_json_response(response)


async def navigate(user_message: str, graph_context: str, user_context: str = "") -> str:
    """Generate a Navigator response."""
    from backend.prompts.navigator import NAVIGATOR_SYSTEM_PROMPT

    system = NAVIGATOR_SYSTEM_PROMPT.format(
        graph_context=graph_context, user_context=user_context,
    )
    return await _call_claude(
        user_message, model=settings.navigator_model, system=system, max_tokens=1500,
    )


async def _call_claude(
    user_message: str,
    model: str | None = None,
    system: str | None = None,
    max_tokens: int = 1500,
    temperature: float = 0.3,
) -> str:
    """Low-level Claude API call."""
    headers = {
        "x-api-key": settings.anthropic_api_key,
        "content-type": "application/json",
        "anthropic-version": "2023-06-01",
    }
    body = {
        "model": model or settings.navigator_model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": user_message}],
    }
    if system:
        body["system"] = system

    async with httpx.AsyncClient() as client:
        resp = await client.post(API_URL, json=body, headers=headers, timeout=60)
        resp.raise_for_status()
        return resp.json()["content"][0]["text"]


def _parse_json_response(text: str) -> dict:
    """Extract JSON from Claude's response (handles markdown code blocks)."""
    try:
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        return json.loads(text.strip())
    except (json.JSONDecodeError, IndexError):
        return {"raw_text": text, "parse_error": True}
