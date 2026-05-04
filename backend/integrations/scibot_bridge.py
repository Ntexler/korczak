"""Sci-Bot Bridge — interface to Sci-Hub's Sci-Bot for full-text paper Q&A.

Sci-Bot (sci-bot.ru) has 88M+ full-text papers and answers scientific
questions with citations. Currently no official API — this bridge
provides a ready-to-use interface for when one becomes available,
and a web-based fallback in the meantime.

Status: Alpha (April 2026). Conversation mode coming soon.
Data: Papers up to ~2021 (Sci-Hub upload pause).

Usage:
  result = await query_scibot("What is the evidence for thick description in ethnography?")
  # Returns {answer, references: [{title, url, year}], source: "scibot"}

  url = get_scibot_url("What is thick description?")
  # Returns direct URL to sci-bot.ru with the query
"""

import logging
import re

import httpx

logger = logging.getLogger(__name__)

SCIBOT_BASE = "https://sci-bot.ru"
SCIBOT_API = f"{SCIBOT_BASE}/api"  # Not yet available — placeholder


def get_scibot_url(query: str) -> str:
    """Generate a direct URL to Sci-Bot with a pre-filled query.

    Users can click this to get a full-text-grounded answer on sci-bot.ru.
    """
    from urllib.parse import quote
    return f"{SCIBOT_BASE}/?q={quote(query)}"


async def query_scibot(query: str) -> dict:
    """Query Sci-Bot for a full-text-grounded answer.

    Tries the API endpoint first. If not available (current state),
    returns a redirect URL instead.

    Returns:
      {
        "status": "api_response" | "redirect" | "unavailable",
        "answer": str | None,
        "references": [{title, url, year}],
        "redirect_url": str,
        "source": "scibot"
      }
    """
    # Try API (for when it becomes available)
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{SCIBOT_API}/ask",
                json={"question": query},
                timeout=30,
            )
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "status": "api_response",
                    "answer": data.get("answer", ""),
                    "references": data.get("references", []),
                    "redirect_url": get_scibot_url(query),
                    "source": "scibot",
                }
    except Exception:
        pass  # Expected — API not yet available

    # Fallback: return redirect URL
    return {
        "status": "redirect",
        "answer": None,
        "references": [],
        "redirect_url": get_scibot_url(query),
        "source": "scibot",
        "note": "Sci-Bot API not yet available. Click the link to query directly.",
    }


async def search_scihub_by_doi(doi: str) -> dict | None:
    """Check if a paper exists on Sci-Hub by DOI.

    Returns {available: bool, url: str} — does NOT download the paper.
    """
    try:
        url = f"https://sci-hub.se/{doi}"
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.head(url, timeout=10)
            return {
                "available": resp.status_code == 200,
                "url": url if resp.status_code == 200 else None,
                "doi": doi,
            }
    except Exception:
        return {"available": False, "url": None, "doi": doi}
