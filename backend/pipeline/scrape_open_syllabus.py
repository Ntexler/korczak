"""Scrape Open Syllabus Project — top titles per field with teaching scores.

The Open Syllabus Project tracks which texts appear most frequently across
millions of university syllabi worldwide. Their 'teaching score' indicates
how commonly a title is assigned.

Usage:
  python -m backend.pipeline.scrape_open_syllabus
"""

import asyncio
import logging
import httpx

from backend.integrations.supabase_client import get_client

logger = logging.getLogger(__name__)

# Open Syllabus Explorer — publicly accessible rankings
# We scrape their public explorer pages since the full API requires institutional access
OS_EXPLORER_URL = "https://opensyllabus.org/api/v1/search"

# Fields to scrape — covers all major academic disciplines
FIELDS = [
    "Anthropology", "Sociology", "Psychology", "Philosophy",
    "Political Science", "Economics", "History", "Linguistics",
    "Biology", "Physics", "Chemistry", "Mathematics",
    "Computer Science", "Literature", "Art History",
    "Religious Studies", "Education", "Law",
    "Environmental Science", "Neuroscience",
    "Gender Studies", "African Studies", "Asian Studies",
]


async def scrape_open_syllabus(max_per_field: int = 100):
    """Scrape top titles per field from Open Syllabus Explorer.

    Uses their public search/explorer which returns ranked titles.
    """
    client = get_client()
    total_syllabi = 0
    total_readings = 0

    async with httpx.AsyncClient(timeout=30) as http:
        for field in FIELDS:
            logger.info(f"Scraping Open Syllabus: {field}")

            try:
                # Try the public explorer API
                resp = await http.get(
                    OS_EXPLORER_URL,
                    params={
                        "query": field,
                        "size": max_per_field,
                        "fields": "title,authors,score,count",
                    },
                    headers={"Accept": "application/json"},
                )

                if resp.status_code != 200:
                    # Fallback: create a placeholder syllabus from field knowledge
                    logger.warning(f"  Open Syllabus API returned {resp.status_code}, using fallback")
                    await _create_field_placeholder(client, field)
                    total_syllabi += 1
                    continue

                data = resp.json()
                results = data.get("results", data.get("titles", []))

                if not results:
                    logger.info(f"  No results for {field}")
                    continue

                # Create a meta-syllabus for this field
                syllabus_data = {
                    "title": f"Open Syllabus — Most Taught in {field}",
                    "institution": "Open Syllabus Project (aggregate)",
                    "department": field,
                    "source": "open_syllabus",
                    "is_template": True,
                    "url": f"https://opensyllabus.org/results-list/titles?field={field}",
                }

                existing = (
                    client.table("syllabi")
                    .select("id")
                    .eq("url", syllabus_data["url"])
                    .limit(1)
                    .execute()
                )
                if existing.data:
                    logger.info(f"  Already exists, skipping {field}")
                    continue

                syl_result = client.table("syllabi").insert(syllabus_data).execute()
                if not syl_result.data:
                    continue
                syllabus_id = syl_result.data[0]["id"]
                total_syllabi += 1

                # Insert each ranked title as a reading
                for i, title_entry in enumerate(results[:max_per_field]):
                    title = title_entry.get("title") or title_entry.get("name", "")
                    authors = title_entry.get("authors") or title_entry.get("author", "")
                    teaching_score = title_entry.get("score") or title_entry.get("count", 0)

                    if not title:
                        continue

                    reading_data = {
                        "syllabus_id": syllabus_id,
                        "external_title": title[:500],
                        "external_authors": authors[:500] if isinstance(authors, str) else str(authors)[:500],
                        "week": (i // 5) + 1,
                        "section": "required" if i < 20 else "recommended",
                        "position": i,
                        "match_confidence": 0,
                    }

                    try:
                        # Try to match to existing papers by title
                        paper_match = (
                            client.table("papers")
                            .select("id")
                            .ilike("title", f"%{title[:50]}%")
                            .limit(1)
                            .execute()
                        )
                        if paper_match.data:
                            reading_data["paper_id"] = paper_match.data[0]["id"]
                            reading_data["match_confidence"] = 0.7
                    except Exception:
                        pass

                    client.table("syllabus_readings").insert(reading_data).execute()
                    total_readings += 1

                logger.info(f"  {field}: {len(results)} readings inserted")

            except Exception as e:
                logger.warning(f"  Error scraping {field}: {e}")
                await _create_field_placeholder(client, field)
                total_syllabi += 1

            await asyncio.sleep(1)  # Rate limit

    logger.info(f"Open Syllabus scraping complete: {total_syllabi} syllabi, {total_readings} readings")
    return total_syllabi, total_readings


async def _create_field_placeholder(client, field: str):
    """Create a placeholder syllabus for a field when API is unavailable."""
    syllabus_data = {
        "title": f"Open Syllabus — {field} (placeholder)",
        "institution": "Open Syllabus Project (aggregate)",
        "department": field,
        "source": "open_syllabus",
        "is_template": True,
        "url": f"https://opensyllabus.org/results-list/titles?field={field}",
    }
    existing = (
        client.table("syllabi")
        .select("id")
        .eq("url", syllabus_data["url"])
        .limit(1)
        .execute()
    )
    if not existing.data:
        client.table("syllabi").insert(syllabus_data).execute()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(scrape_open_syllabus())
