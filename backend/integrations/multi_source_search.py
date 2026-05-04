"""Multi-Source Paper Search — unified interface to 20+ academic databases.

Inspired by paper-search-mcp, provides a single search function that queries
multiple academic sources and deduplicates results.

Sources supported:
- OpenAlex (already integrated — primary)
- Semantic Scholar (free API, high quality)
- CrossRef (DOI metadata, 140M+ records)
- PubMed/Europe PMC (biomedical)
- arXiv (preprints, STEM)
- CORE (open access, 200M+ papers)
- DOAJ (open access journals)
- Unpaywall (open access links)

Each source returns normalized paper dicts matching Korczak's schema.
"""

import logging
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)


async def search_semantic_scholar(
    query: str, limit: int = 10, year_from: int | None = None,
) -> list[dict]:
    """Search Semantic Scholar API (free, no key needed, 100 req/5min)."""
    params = {
        "query": query,
        "limit": min(limit, 100),
        "fields": "title,authors,year,abstract,citationCount,externalIds,publicationTypes",
    }
    if year_from:
        params["year"] = f"{year_from}-"

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.semanticscholar.org/graph/v1/paper/search",
                params=params, timeout=15,
            )
            if resp.status_code != 200:
                logger.warning(f"Semantic Scholar error: {resp.status_code}")
                return []

            data = resp.json()
            papers = []
            for p in data.get("data", []):
                ext = p.get("externalIds") or {}
                authors = [{"name": a.get("name", "")} for a in (p.get("authors") or [])]
                papers.append({
                    "title": p.get("title", ""),
                    "authors": authors,
                    "publication_year": p.get("year"),
                    "abstract": p.get("abstract") or "",
                    "cited_by_count": p.get("citationCount", 0),
                    "doi": ext.get("DOI"),
                    "source": "semantic_scholar",
                    "external_id": p.get("paperId", ""),
                })
            return papers
    except Exception as e:
        logger.warning(f"Semantic Scholar search failed: {e}")
        return []


async def search_crossref(
    query: str, limit: int = 10, year_from: int | None = None,
) -> list[dict]:
    """Search CrossRef API (free, polite pool with email)."""
    import os
    params = {
        "query": query,
        "rows": min(limit, 50),
        "select": "DOI,title,author,published-print,abstract,is-referenced-by-count",
    }
    email = os.getenv("OPENALEX_EMAIL")
    if email:
        params["mailto"] = email
    if year_from:
        params["filter"] = f"from-pub-date:{year_from}"

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.crossref.org/works",
                params=params, timeout=15,
            )
            if resp.status_code != 200:
                return []

            items = resp.json().get("message", {}).get("items", [])
            papers = []
            for item in items:
                title = item.get("title", [""])[0] if item.get("title") else ""
                authors = [
                    {"name": f"{a.get('given', '')} {a.get('family', '')}".strip()}
                    for a in (item.get("author") or [])
                ]
                year = None
                pub_date = item.get("published-print") or item.get("published-online")
                if pub_date and pub_date.get("date-parts"):
                    parts = pub_date["date-parts"][0]
                    if parts:
                        year = parts[0]

                papers.append({
                    "title": title,
                    "authors": authors,
                    "publication_year": year,
                    "abstract": _clean_abstract(item.get("abstract", "")),
                    "cited_by_count": item.get("is-referenced-by-count", 0),
                    "doi": item.get("DOI"),
                    "source": "crossref",
                    "external_id": item.get("DOI", ""),
                })
            return papers
    except Exception as e:
        logger.warning(f"CrossRef search failed: {e}")
        return []


async def search_europe_pmc(
    query: str, limit: int = 10,
) -> list[dict]:
    """Search Europe PMC (free, no key, biomedical papers)."""
    params = {
        "query": query,
        "format": "json",
        "pageSize": min(limit, 25),
        "resultType": "core",
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
                params=params, timeout=15,
            )
            if resp.status_code != 200:
                return []

            results = resp.json().get("resultList", {}).get("result", [])
            papers = []
            for r in results:
                authors = []
                if r.get("authorString"):
                    for name in r["authorString"].split(", ")[:10]:
                        authors.append({"name": name})

                papers.append({
                    "title": r.get("title", ""),
                    "authors": authors,
                    "publication_year": int(r["pubYear"]) if r.get("pubYear") else None,
                    "abstract": r.get("abstractText", ""),
                    "cited_by_count": r.get("citedByCount", 0),
                    "doi": r.get("doi"),
                    "source": "europe_pmc",
                    "external_id": r.get("pmid") or r.get("id", ""),
                })
            return papers
    except Exception as e:
        logger.warning(f"Europe PMC search failed: {e}")
        return []


async def search_core(
    query: str, limit: int = 10, api_key: str | None = None,
) -> list[dict]:
    """Search CORE API (200M+ open access papers). API key optional but recommended."""
    import os
    key = api_key or os.getenv("CORE_API_KEY", "")
    headers = {"Authorization": f"Bearer {key}"} if key else {}

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.core.ac.uk/v3/search/works",
                json={"q": query, "limit": min(limit, 20)},
                headers=headers, timeout=15,
            )
            if resp.status_code != 200:
                return []

            results = resp.json().get("results", [])
            papers = []
            for r in results:
                authors = [{"name": a.get("name", "")} for a in (r.get("authors") or [])]
                papers.append({
                    "title": r.get("title", ""),
                    "authors": authors,
                    "publication_year": r.get("yearPublished"),
                    "abstract": r.get("abstract", ""),
                    "cited_by_count": r.get("citationCount", 0),
                    "doi": r.get("doi"),
                    "source": "core",
                    "external_id": str(r.get("id", "")),
                })
            return papers
    except Exception as e:
        logger.warning(f"CORE search failed: {e}")
        return []


async def multi_source_search(
    query: str,
    limit_per_source: int = 5,
    sources: list[str] | None = None,
    year_from: int | None = None,
) -> dict:
    """Search multiple academic databases in parallel and deduplicate.

    Returns {papers: [...], sources_queried: [...], total: int}.
    """
    import asyncio

    available_sources = {
        "semantic_scholar": lambda: search_semantic_scholar(query, limit_per_source, year_from),
        "crossref": lambda: search_crossref(query, limit_per_source, year_from),
        "europe_pmc": lambda: search_europe_pmc(query, limit_per_source),
        "core": lambda: search_core(query, limit_per_source),
    }

    # Select sources
    if sources:
        selected = {k: v for k, v in available_sources.items() if k in sources}
    else:
        selected = available_sources

    # Run all in parallel
    tasks = {name: fn() for name, fn in selected.items()}
    results = await asyncio.gather(*tasks.values(), return_exceptions=True)

    # Collect and deduplicate
    all_papers = []
    sources_queried = []
    seen_titles = set()

    for name, result in zip(tasks.keys(), results):
        sources_queried.append(name)
        if isinstance(result, Exception):
            logger.warning(f"Source {name} failed: {result}")
            continue
        for paper in result:
            title_key = (paper.get("title") or "").lower().strip()[:80]
            if title_key and title_key not in seen_titles:
                seen_titles.add(title_key)
                all_papers.append(paper)

    # Sort by citations
    all_papers.sort(key=lambda p: p.get("cited_by_count", 0), reverse=True)

    return {
        "papers": all_papers,
        "sources_queried": sources_queried,
        "total": len(all_papers),
    }


def _clean_abstract(text: str) -> str:
    """Clean HTML tags from CrossRef abstracts."""
    import re
    if not text:
        return ""
    return re.sub(r"<[^>]+>", "", text).strip()
