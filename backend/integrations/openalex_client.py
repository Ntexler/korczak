"""OpenAlex API client for fetching academic papers."""

import httpx

from backend.config import settings

BASE_URL = "https://api.openalex.org"

# Anthropology topic ID in OpenAlex
ANTHROPOLOGY_TOPIC = "https://openalex.org/T10149"


async def fetch_papers(
    topic_id: str = ANTHROPOLOGY_TOPIC,
    from_year: int = 2024,
    to_year: int = 2025,
    per_page: int = 50,
    cursor: str = "*",
) -> dict:
    """Fetch papers from OpenAlex with cursor pagination."""
    params = {
        "filter": (
            f"topics.id:{topic_id},"
            f"from_publication_date:{from_year}-01-01,"
            f"to_publication_date:{to_year}-12-31,"
            f"has_abstract:true,language:en,type:article"
        ),
        "sort": "cited_by_count:desc",
        "per_page": per_page,
        "cursor": cursor,
        "select": (
            "id,title,authorships,publication_year,abstract_inverted_index,"
            "cited_by_count,doi,primary_location,topics,concepts"
        ),
    }
    if settings.openalex_email:
        params["mailto"] = settings.openalex_email

    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{BASE_URL}/works", params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

    return {
        "papers": [_normalize_paper(p) for p in data.get("results", [])],
        "next_cursor": data.get("meta", {}).get("next_cursor"),
        "total_count": data.get("meta", {}).get("count", 0),
    }


async def search_papers_by_keyword(
    keyword: str,
    from_year: int | None = None,
    limit: int = 10,
) -> list[dict]:
    """Search OpenAlex for papers matching a keyword (uses the search parameter)."""
    params = {
        "search": keyword,
        "per_page": limit,
        "sort": "relevance_score:desc",
        "select": (
            "id,title,authorships,publication_year,abstract_inverted_index,"
            "cited_by_count,doi,primary_location"
        ),
    }
    if from_year:
        params["filter"] = f"from_publication_date:{from_year}-01-01,has_abstract:true"
    else:
        params["filter"] = "has_abstract:true"

    if settings.openalex_email:
        params["mailto"] = settings.openalex_email

    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{BASE_URL}/works", params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

    return [_normalize_paper(p) for p in data.get("results", [])]


def _normalize_paper(raw: dict) -> dict:
    """Normalize OpenAlex paper format to our internal format."""
    return {
        "openalex_id": (raw.get("id") or "").split("/")[-1],
        "title": raw.get("title", ""),
        "authors": _extract_authors(raw.get("authorships", [])),
        "publication_year": raw.get("publication_year"),
        "abstract": reconstruct_abstract(raw.get("abstract_inverted_index")),
        "doi": raw.get("doi"),
        "cited_by_count": raw.get("cited_by_count", 0),
        "source_journal": (
            (raw.get("primary_location") or {}).get("source") or {}
        ).get("display_name"),
    }


def _extract_authors(authorships: list) -> list[dict]:
    """Extract structured author info from OpenAlex authorships."""
    authors = []
    for a in authorships:
        author = a.get("author", {})
        institution = (
            a.get("institutions", [{}])[0].get("display_name")
            if a.get("institutions")
            else None
        )
        authors.append({
            "name": author.get("display_name", "Unknown"),
            "openalex_id": (author.get("id") or "").split("/")[-1],
            "orcid": author.get("orcid"),
            "institution": institution,
        })
    return authors


def reconstruct_abstract(inverted_index: dict | None) -> str:
    """Reconstruct abstract from OpenAlex inverted index format."""
    if not inverted_index:
        return ""
    word_positions = []
    for word, positions in inverted_index.items():
        for pos in positions:
            word_positions.append((pos, word))
    word_positions.sort()
    return " ".join(w for _, w in word_positions)
