"""Claude API client — abstraction layer for LLM calls."""

import json
import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

from backend.config import settings

API_URL = "https://api.anthropic.com/v1/messages"


@dataclass
class ClaudeResponse:
    """Response from Claude API with token usage."""
    text: str
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


async def analyze_paper(title: str, authors: str, year: int, abstract: str) -> dict:
    """Analyze a paper using the Phase 0.5 prompt."""
    from backend.prompts.paper_analysis import ANALYSIS_PROMPT

    prompt = ANALYSIS_PROMPT.format(
        title=title, authors=authors, year=year, abstract=abstract,
    )
    response = await _call_claude(prompt, model=settings.analysis_model, max_tokens=2000)
    return _parse_json_response(response.text)


async def navigate(
    user_message: str,
    graph_context: str,
    user_context: str = "",
    history: list[dict] | None = None,
) -> str:
    """Generate a Navigator response with optional conversation history."""
    from backend.prompts.navigator import NAVIGATOR_SYSTEM_PROMPT

    system = NAVIGATOR_SYSTEM_PROMPT.format(
        graph_context=graph_context, user_context=user_context,
    )

    if history:
        # Build full messages array: last 3 exchanges + current message
        messages = []
        for msg in history[-6:]:  # Last 3 exchanges = 6 messages max
            messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": user_message})
        result = await _call_claude_messages(
            messages=messages, model=settings.navigator_model, system=system, max_tokens=1500,
        )
    else:
        result = await _call_claude(
            user_message, model=settings.navigator_model, system=system, max_tokens=1500,
        )
    return result.text


async def tutor(
    user_message: str,
    graph_context: str,
    user_context: str = "",
    level_description: str = "",
    socratic_level: int = 0,
    history: list[dict] | None = None,
) -> str:
    """Generate a Socratic Tutor response."""
    from backend.prompts.tutor import build_tutor_prompt

    system = build_tutor_prompt(
        graph_context=graph_context,
        user_context=user_context,
        level_description=level_description,
        socratic_level=socratic_level,
    )

    if history:
        messages = []
        for msg in history[-6:]:
            messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": user_message})
        result = await _call_claude_messages(
            messages=messages, model=settings.navigator_model, system=system,
            max_tokens=1200, temperature=0.4,
        )
    else:
        result = await _call_claude(
            user_message, model=settings.navigator_model, system=system,
            max_tokens=1200, temperature=0.4,
        )
    return result.text


async def _call_claude(
    user_message: str,
    model: str | None = None,
    system: str | None = None,
    max_tokens: int = 1500,
    temperature: float = 0.3,
) -> ClaudeResponse:
    """Low-level Claude API call. Returns ClaudeResponse with text + token counts."""
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
        if resp.status_code != 200:
            error_body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            error_msg = error_body.get("error", {}).get("message", resp.text)
            logger.error(f"Claude API error {resp.status_code}: {error_msg}")
            raise RuntimeError(f"Claude API error: {error_msg}")
        data = resp.json()
        usage = data.get("usage", {})
        return ClaudeResponse(
            text=data["content"][0]["text"],
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
        )


async def _call_claude_messages(
    messages: list[dict],
    model: str | None = None,
    system: str | None = None,
    max_tokens: int = 1500,
    temperature: float = 0.3,
) -> ClaudeResponse:
    """Claude API call with full messages array (for multi-turn). Returns ClaudeResponse."""
    headers = {
        "x-api-key": settings.anthropic_api_key,
        "content-type": "application/json",
        "anthropic-version": "2023-06-01",
    }
    body = {
        "model": model or settings.navigator_model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": messages,
    }
    if system:
        body["system"] = system

    async with httpx.AsyncClient() as client:
        resp = await client.post(API_URL, json=body, headers=headers, timeout=60)
        if resp.status_code != 200:
            error_body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            error_msg = error_body.get("error", {}).get("message", resp.text)
            logger.error(f"Claude API error {resp.status_code}: {error_msg}")
            raise RuntimeError(f"Claude API error: {error_msg}")
        data = resp.json()
        usage = data.get("usage", {})
        return ClaudeResponse(
            text=data["content"][0]["text"],
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
        )


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
