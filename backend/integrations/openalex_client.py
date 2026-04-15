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
            "cited_by_count,doi,primary_location,topics,concepts,grants,open_access"
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
            "cited_by_count,doi,primary_location,grants,open_access"
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
    """Normalize OpenAlex paper format to our internal format.

    Includes Feature 6.5 enrichments: funding from `grants`, country +
    ROR ID per author (when OpenAlex provides them), and open-access
    status signals.
    """
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
        "funding": _extract_funding(raw.get("grants") or []),
        "open_access": (raw.get("open_access") or {}).get("is_oa"),
    }


def _extract_authors(authorships: list) -> list[dict]:
    """Extract structured author info from OpenAlex authorships.

    Enrichments (Feature 6.5):
      - `institution_ror_id`: ROR ID of the first listed institution, if present
      - `country`: ISO country code of the first listed institution, if present
      - `institutions`: full list of authorship institutions (name / ror / country),
        useful when a paper has multi-affiliation authors
    """
    authors = []
    for a in authorships:
        author = a.get("author", {})
        institutions_raw = a.get("institutions") or []
        institutions = [
            {
                "name": inst.get("display_name"),
                "ror_id": inst.get("ror"),
                "country": inst.get("country_code"),
            }
            for inst in institutions_raw
            if inst
        ]
        primary = institutions[0] if institutions else {}
        authors.append({
            "name": author.get("display_name", "Unknown"),
            "openalex_id": (author.get("id") or "").split("/")[-1],
            "orcid": author.get("orcid"),
            "institution": primary.get("name"),
            "institution_ror_id": primary.get("ror_id"),
            "country": primary.get("country"),
            "institutions": institutions,
        })
    return authors


def _extract_funding(grants: list) -> list[dict]:
    """Extract funding info from OpenAlex `grants` array.

    OpenAlex grant shape: {funder, funder_display_name, award_id}
    Our target shape (per migration 001): [{funder, grant_id, funder_id}]
    """
    funding = []
    for g in grants or []:
        funder_id = (g.get("funder") or "").rsplit("/", 1)[-1] if g.get("funder") else None
        funding.append({
            "funder": g.get("funder_display_name") or funder_id,
            "funder_id": funder_id,
            "grant_id": g.get("award_id"),
        })
    return funding


async def fetch_work_by_id(openalex_id: str) -> dict | None:
    """Fetch a single work by its OpenAlex ID with full enrichment fields.

    Used by backfill scripts that need to re-pull a paper to populate
    grants / country / open-access details that weren't requested in the
    original seeding.
    """
    clean_id = openalex_id.rsplit("/", 1)[-1]
    params = {
        "select": (
            "id,title,authorships,publication_year,abstract_inverted_index,"
            "cited_by_count,doi,primary_location,grants,open_access"
        ),
    }
    if settings.openalex_email:
        params["mailto"] = settings.openalex_email

    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{BASE_URL}/works/{clean_id}", params=params, timeout=20)
        if resp.status_code != 200:
            return None
        return _normalize_paper(resp.json())


async def fetch_author_by_id(openalex_id: str) -> dict | None:
    """Fetch an OpenAlex author profile for enrichment (Feature 6.5).

    Returns a dict with: id, display_name, orcid, works_count, cited_by_count,
    summary_stats.h_index, last_known_institution (name / country / ror),
    x_concepts (top concepts), affiliations history.
    """
    clean_id = openalex_id.rsplit("/", 1)[-1]
    params = {
        "select": (
            "id,display_name,orcid,works_count,cited_by_count,summary_stats,"
            "last_known_institutions,affiliations,x_concepts"
        ),
    }
    if settings.openalex_email:
        params["mailto"] = settings.openalex_email

    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{BASE_URL}/authors/{clean_id}", params=params, timeout=20)
        if resp.status_code != 200:
            return None
        return resp.json()


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
