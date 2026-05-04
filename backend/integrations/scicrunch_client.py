"""SciCrunch RRID Client — enrich papers with Research Resource Identifiers.

RRIDs are persistent identifiers for research resources:
- Antibodies (AB_*)
- Cell lines (CVCL_*)
- Software tools (SCR_*)
- Organisms (IMSR_*, MMRRC_*)
- Plasmids, datasets, etc.

Over 1,000 journals require RRIDs. 500K+ RRIDs cited in literature.
SciCrunch resolver API is free and open.

Usage:
  resources = await lookup_rrid("AB_2313773")
  resources = await search_resources("ImageJ", category="software")
"""

import logging

import httpx

logger = logging.getLogger(__name__)

SCICRUNCH_API = "https://scicrunch.org/api/1"
RESOLVER_API = "https://scicrunch.org/resolver"


async def lookup_rrid(rrid: str) -> dict | None:
    """Look up a specific RRID and get resource metadata.

    Returns {name, type, description, vendor, url, citations} or None.
    """
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{RESOLVER_API}/{rrid}.json",
                timeout=10,
            )
            if resp.status_code != 200:
                return None

            data = resp.json()
            if not data:
                return None

            # Extract from various response formats
            hit = data if isinstance(data, dict) else data[0] if isinstance(data, list) and data else {}

            return {
                "rrid": rrid,
                "name": hit.get("name", ""),
                "type": hit.get("type", ""),
                "description": hit.get("description", ""),
                "vendor": hit.get("vendor", {}).get("name", "") if isinstance(hit.get("vendor"), dict) else "",
                "url": hit.get("url", ""),
                "citation_count": hit.get("citation_count", 0),
            }
    except Exception as e:
        logger.warning(f"RRID lookup failed for {rrid}: {e}")
        return None


async def search_resources(
    query: str,
    category: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """Search SciCrunch for research resources by name/keyword.

    category: "antibody", "software", "cell_line", "organism", "plasmid"
    """
    params = {
        "q": query,
        "limit": min(limit, 20),
    }
    if category:
        params["category"] = category

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{SCICRUNCH_API}/resource/fields/search",
                params=params, timeout=10,
            )
            if resp.status_code != 200:
                return []

            results = resp.json().get("result", [])
            resources = []
            for r in results:
                resources.append({
                    "rrid": r.get("rid", ""),
                    "name": r.get("resource_name", ""),
                    "type": r.get("type", ""),
                    "description": r.get("description", "")[:300] if r.get("description") else "",
                    "url": r.get("url", ""),
                })
            return resources
    except Exception as e:
        logger.warning(f"SciCrunch search failed: {e}")
        return []


async def extract_rrids_from_text(text: str) -> list[str]:
    """Extract RRID patterns from paper text."""
    import re
    pattern = r'RRID:\s*([A-Za-z]+_[A-Za-z0-9]+)'
    matches = re.findall(pattern, text)
    return list(set(matches))


async def enrich_paper_with_resources(
    paper_id: str,
    abstract: str,
) -> list[dict]:
    """Find and resolve RRIDs mentioned in a paper's abstract.

    Returns list of resolved resources.
    """
    rrids = await extract_rrids_from_text(abstract)
    if not rrids:
        return []

    resources = []
    for rrid in rrids[:10]:  # cap at 10 lookups
        resource = await lookup_rrid(rrid)
        if resource:
            resource["paper_id"] = paper_id
            resources.append(resource)

    return resources
