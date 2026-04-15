"""arXiv source — preprint lookup for papers that also exist on arXiv.

arXiv indexes DOI for many papers, and also papers that originated as
preprints. When we get a hit, we return the abstract + the arXiv URL.
For humanities papers (anthropology, philosophy), hit rate is low; for
STEM it's high.
"""

import re

import httpx

from backend.core.provenance.types import ExtractionContext, SourceResult


ARXIV_QUERY_URL = "http://export.arxiv.org/api/query"


def _parse_arxiv_entry(xml: str) -> tuple[str, str, str] | None:
    """Return (title, summary, id_url) from an Atom feed entry, or None."""
    title_match = re.search(r"<entry>.*?<title>(.*?)</title>", xml, re.DOTALL)
    summary_match = re.search(r"<entry>.*?<summary>(.*?)</summary>", xml, re.DOTALL)
    id_match = re.search(r"<entry>.*?<id>(.*?)</id>", xml, re.DOTALL)
    if not (title_match and summary_match and id_match):
        return None
    return (
        re.sub(r"\s+", " ", title_match.group(1)).strip(),
        re.sub(r"\s+", " ", summary_match.group(1)).strip(),
        id_match.group(1).strip(),
    )


async def fetch(ctx: ExtractionContext) -> SourceResult:
    # arXiv search is noisy with a raw title. Use DOI when we have it.
    if not (ctx.doi or ctx.title):
        return SourceResult(source="arxiv", status="miss", error="no DOI or title")

    if ctx.doi:
        query = f'doi:"{ctx.doi}"'
    else:
        # Title-only search as a fallback. arXiv's API escaping is minimal; strip quotes.
        title = (ctx.title or "").replace('"', "").strip()
        if len(title) < 10:
            return SourceResult(source="arxiv", status="miss", error="title too short")
        query = f'ti:"{title}"'

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                ARXIV_QUERY_URL,
                params={"search_query": query, "max_results": 1},
                timeout=15,
            )
    except Exception as e:
        return SourceResult(source="arxiv", status="error", error=str(e))

    if resp.status_code != 200:
        return SourceResult(source="arxiv", status="miss", error=f"HTTP {resp.status_code}")

    parsed = _parse_arxiv_entry(resp.text)
    if not parsed:
        return SourceResult(source="arxiv", status="miss", error="no entry found")

    title, summary, id_url = parsed

    # Sanity check — require title overlap when the search was by title
    if not ctx.doi:
        if not _title_similar_enough(ctx.title or "", title):
            return SourceResult(source="arxiv", status="miss", error="title mismatch")

    return SourceResult(
        source="arxiv",
        status="hit",
        passages=[summary] if summary else [],
        location_hints=["arXiv abstract"] if summary else [],
        url=id_url,
    )


def _title_similar_enough(a: str, b: str) -> bool:
    a_words = set(re.findall(r"[a-z]+", a.lower()))
    b_words = set(re.findall(r"[a-z]+", b.lower()))
    if not a_words:
        return False
    overlap = len(a_words & b_words) / len(a_words)
    return overlap >= 0.6
