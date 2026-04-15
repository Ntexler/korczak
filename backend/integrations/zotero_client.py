"""Zotero Integration — import user's Zotero library into Korczak.

Uses the Zotero Web API v3 to fetch a user's library and map papers
to the Korczak knowledge graph via DOI/title matching.

API docs: https://www.zotero.org/support/dev/web_api/v3/start
"""

import logging

import httpx

from backend.integrations.supabase_client import get_client

logger = logging.getLogger(__name__)

ZOTERO_API = "https://api.zotero.org"


async def fetch_zotero_library(
    user_or_group_id: str,
    api_key: str,
    library_type: str = "users",
    limit: int = 100,
) -> list[dict]:
    """Fetch items from a Zotero library.

    Returns a list of simplified item dicts with:
    - title, authors, year, doi, abstract, item_type, tags
    """
    headers = {
        "Zotero-API-Key": api_key,
        "Zotero-API-Version": "3",
    }

    items = []
    start = 0

    async with httpx.AsyncClient() as client:
        while start < limit:
            batch_size = min(50, limit - start)
            url = f"{ZOTERO_API}/{library_type}/{user_or_group_id}/items"
            params = {
                "format": "json",
                "limit": batch_size,
                "start": start,
                "itemType": "-attachment || note",
                "sort": "dateModified",
                "direction": "desc",
            }

            resp = await client.get(url, headers=headers, params=params, timeout=30)
            if resp.status_code != 200:
                logger.error(f"Zotero API error {resp.status_code}: {resp.text[:200]}")
                break

            batch = resp.json()
            if not batch:
                break

            for item in batch:
                data = item.get("data", {})
                item_type = data.get("itemType", "")

                # Skip non-paper types
                if item_type in ("attachment", "note", "annotation"):
                    continue

                # Extract authors
                creators = data.get("creators", [])
                authors = []
                for c in creators:
                    name = f"{c.get('firstName', '')} {c.get('lastName', '')}".strip()
                    if name:
                        authors.append({"name": name})

                # Extract DOI
                doi = data.get("DOI", "") or ""
                if not doi:
                    extra = data.get("extra", "")
                    if "DOI:" in extra:
                        doi = extra.split("DOI:")[1].strip().split()[0]

                # Extract year
                date = data.get("date", "")
                year = None
                if date:
                    import re
                    year_match = re.search(r"(\d{4})", date)
                    if year_match:
                        year = int(year_match.group(1))

                items.append({
                    "zotero_key": item.get("key", ""),
                    "title": data.get("title", ""),
                    "authors": authors,
                    "year": year,
                    "doi": doi,
                    "abstract": data.get("abstractNote", ""),
                    "item_type": item_type,
                    "tags": [t.get("tag", "") for t in data.get("tags", [])],
                    "url": data.get("url", ""),
                    "publication": data.get("publicationTitle", ""),
                })

            start += len(batch)
            if len(batch) < batch_size:
                break

    logger.info(f"Fetched {len(items)} items from Zotero")
    return items


async def match_zotero_to_korczak(
    zotero_items: list[dict],
) -> dict:
    """Match Zotero items to Korczak papers by DOI or title.

    Returns:
    - matched: [{zotero_item, korczak_paper_id, match_method}]
    - unmatched: [zotero_item]
    - concepts_covered: [concept_name] — concepts from matched papers
    """
    client = get_client()

    # Get all papers for DOI matching
    papers = client.table("papers").select(
        "id, title, doi, openalex_id"
    ).execute()

    doi_map: dict[str, str] = {}
    title_map: dict[str, str] = {}
    for p in (papers.data or []):
        if p.get("doi"):
            doi_map[p["doi"].lower().strip()] = p["id"]
        if p.get("title"):
            title_map[p["title"].lower().strip()] = p["id"]

    matched = []
    unmatched = []
    matched_paper_ids = set()

    for item in zotero_items:
        paper_id = None
        method = "none"

        # Try DOI match first
        doi = (item.get("doi") or "").lower().strip()
        if doi and doi in doi_map:
            paper_id = doi_map[doi]
            method = "doi"
        else:
            # Try title match
            title = (item.get("title") or "").lower().strip()
            if title and title in title_map:
                paper_id = title_map[title]
                method = "title"

        if paper_id:
            matched.append({
                "zotero_key": item["zotero_key"],
                "title": item["title"],
                "korczak_paper_id": paper_id,
                "match_method": method,
            })
            matched_paper_ids.add(paper_id)
        else:
            unmatched.append(item)

    # Get concepts covered by matched papers
    concepts_covered = []
    if matched_paper_ids:
        pid_list = list(matched_paper_ids)
        concept_ids = set()
        for i in range(0, len(pid_list), 50):
            batch = pid_list[i:i + 50]
            pc = client.table("paper_concepts").select(
                "concept_id"
            ).in_("paper_id", batch).execute()
            for row in (pc.data or []):
                concept_ids.add(row["concept_id"])

        if concept_ids:
            concepts = client.table("concepts").select(
                "name"
            ).in_("id", list(concept_ids)).execute()
            concepts_covered = [c["name"] for c in (concepts.data or [])]

    return {
        "matched": matched,
        "unmatched_count": len(unmatched),
        "concepts_covered": concepts_covered,
        "total_items": len(zotero_items),
        "match_rate": round(len(matched) / max(len(zotero_items), 1) * 100, 1),
    }
