"""Sci-Bot Scraper — automated querier for sci-bot.ru.

Since Sci-Bot has no API, this uses HTTP requests to interact with the
web interface, extract answers and references, and return structured data.

Approach: POST to sci-bot.ru's chat endpoint (which the frontend uses)
and parse the HTML/JSON response.

Usage:
  result = await ask_scibot("What evidence supports thick description in ethnography?")
  # Returns {answer, references: [{title, authors, year, url}]}

  results = await batch_ask(["question1", "question2", ...])
"""

import logging
import re
import time
import asyncio

import httpx

logger = logging.getLogger(__name__)

SCIBOT_URL = "https://sci-bot.ru"


async def ask_scibot(question: str, timeout: int = 60) -> dict:
    """Send a question to Sci-Bot and get a structured answer.

    Tries to interact with the web endpoint directly.
    Falls back gracefully if blocked or unavailable.
    """
    headers = {
        "User-Agent": "Korczak-AI/1.0 (academic knowledge navigator)",
        "Accept": "application/json, text/html",
        "Content-Type": "application/json",
        "Origin": SCIBOT_URL,
        "Referer": f"{SCIBOT_URL}/",
    }

    # Try JSON API endpoint (common pattern for chat interfaces)
    api_endpoints = [
        f"{SCIBOT_URL}/api/chat",
        f"{SCIBOT_URL}/api/ask",
        f"{SCIBOT_URL}/api/query",
        f"{SCIBOT_URL}/chat",
    ]

    for endpoint in api_endpoints:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    endpoint,
                    json={"question": question, "query": question, "message": question},
                    headers=headers,
                    timeout=timeout,
                )

                if resp.status_code == 200:
                    data = resp.json() if "json" in resp.headers.get("content-type", "") else {}

                    if data:
                        return _parse_api_response(data, question)

                    # Try parsing HTML response
                    if resp.text:
                        return _parse_html_response(resp.text, question)

        except httpx.TimeoutException:
            logger.info(f"Sci-Bot timeout on {endpoint} — question may need longer processing")
            continue
        except Exception as e:
            logger.debug(f"Sci-Bot endpoint {endpoint} failed: {e}")
            continue

    # All endpoints failed — return redirect
    logger.info("Sci-Bot: no API endpoint responded, returning redirect URL")
    return {
        "status": "redirect",
        "answer": None,
        "references": [],
        "question": question,
        "redirect_url": _make_url(question),
        "note": "Sci-Bot did not respond to API calls. Use the redirect URL to query manually.",
    }


def _parse_api_response(data: dict, question: str) -> dict:
    """Parse a JSON response from Sci-Bot."""
    answer = (
        data.get("answer") or data.get("response") or
        data.get("text") or data.get("message") or data.get("content") or ""
    )

    refs = data.get("references") or data.get("sources") or data.get("citations") or []

    parsed_refs = []
    for ref in refs:
        if isinstance(ref, str):
            parsed_refs.append({"title": ref, "url": "", "year": None})
        elif isinstance(ref, dict):
            parsed_refs.append({
                "title": ref.get("title") or ref.get("name", ""),
                "authors": ref.get("authors", ""),
                "year": ref.get("year") or ref.get("date"),
                "url": ref.get("url") or ref.get("link", ""),
                "doi": ref.get("doi", ""),
            })

    return {
        "status": "api_response",
        "answer": answer,
        "references": parsed_refs,
        "question": question,
        "redirect_url": _make_url(question),
    }


def _parse_html_response(html: str, question: str) -> dict:
    """Extract answer and references from HTML response."""
    # Try to find the answer text
    answer = ""

    # Common patterns in chat interfaces
    answer_patterns = [
        r'class="answer[^"]*"[^>]*>(.*?)</div>',
        r'class="response[^"]*"[^>]*>(.*?)</div>',
        r'class="message-content[^"]*"[^>]*>(.*?)</div>',
    ]

    for pattern in answer_patterns:
        match = re.search(pattern, html, re.DOTALL)
        if match:
            answer = re.sub(r"<[^>]+>", "", match.group(1)).strip()
            break

    # Extract references (links to papers)
    ref_pattern = r'href="(https?://sci-hub\.[^"]+)"[^>]*>([^<]+)</a>'
    refs = []
    for match in re.finditer(ref_pattern, html):
        refs.append({
            "url": match.group(1),
            "title": match.group(2).strip(),
        })

    return {
        "status": "html_parsed" if answer else "redirect",
        "answer": answer or None,
        "references": refs,
        "question": question,
        "redirect_url": _make_url(question),
    }


def _make_url(question: str) -> str:
    """Generate redirect URL."""
    from urllib.parse import quote
    return f"{SCIBOT_URL}/?q={quote(question)}"


async def batch_ask(
    questions: list[str],
    delay: float = 3.0,
    max_concurrent: int = 1,
) -> list[dict]:
    """Ask multiple questions with rate limiting.

    Be polite: 3s delay between requests, sequential by default.
    """
    results = []
    for i, question in enumerate(questions):
        logger.info(f"Sci-Bot batch [{i+1}/{len(questions)}]: {question[:60]}...")
        result = await ask_scibot(question)
        results.append(result)
        if i < len(questions) - 1:
            await asyncio.sleep(delay)
    return results
