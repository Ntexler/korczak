"""Scrape Coursera + edX — public course catalogs with syllabus outlines.

Both platforms have publicly accessible course metadata.

Usage:
  python -m backend.pipeline.scrape_coursera
"""

import asyncio
import logging
import httpx

from backend.integrations.supabase_client import get_client

logger = logging.getLogger(__name__)

COURSERA_API = "https://api.coursera.org/api/courses.v1"
EDX_CATALOG = "https://courses.edx.org/api/courses/v1/courses/"

# Search queries to cover all major academic fields
SEARCH_QUERIES = [
    "anthropology", "sociology", "psychology", "philosophy",
    "linguistics", "political science", "economics", "history",
    "biology", "neuroscience", "cognitive science", "physics",
    "chemistry", "mathematics", "computer science", "statistics",
    "literature", "art history", "religious studies", "education",
    "environmental science", "gender studies", "public health",
    "law", "business", "data science", "artificial intelligence",
]


async def scrape_coursera(max_per_query: int = 20):
    """Scrape Coursera course catalog."""
    client = get_client()
    total_syllabi = 0

    async with httpx.AsyncClient(timeout=30) as http:
        for query in SEARCH_QUERIES:
            logger.info(f"Scraping Coursera: {query}")

            try:
                resp = await http.get(
                    COURSERA_API,
                    params={
                        "q": "search",
                        "query": query,
                        "limit": max_per_query,
                        "fields": "name,slug,description,partnerIds,primaryLanguages",
                        "includes": "partnerIds",
                    },
                )

                if resp.status_code != 200:
                    logger.warning(f"  Coursera API returned {resp.status_code}")
                    continue

                data = resp.json()
                courses = data.get("elements", [])

                for course in courses:
                    name = course.get("name", "")
                    slug = course.get("slug", "")
                    description = course.get("description", "")

                    if not name:
                        continue

                    url = f"https://www.coursera.org/learn/{slug}" if slug else ""

                    existing = (
                        client.table("syllabi")
                        .select("id")
                        .eq("title", name)
                        .eq("source", "coursera")
                        .limit(1)
                        .execute()
                    )
                    if existing.data:
                        continue

                    # Determine department from query
                    department = query.replace("_", " ").title()

                    syllabus_data = {
                        "title": name,
                        "institution": "Coursera (multiple universities)",
                        "department": department,
                        "url": url,
                        "source": "coursera",
                        "is_template": True,
                    }

                    syl_result = client.table("syllabi").insert(syllabus_data).execute()
                    if syl_result.data and description:
                        total_syllabi += 1
                        syllabus_id = syl_result.data[0]["id"]

                        # Store course description as context
                        client.table("syllabus_readings").insert({
                            "syllabus_id": syllabus_id,
                            "external_title": f"Course overview: {description[:400]}",
                            "week": 1,
                            "section": "supplementary",
                            "position": 0,
                            "match_confidence": 0,
                        }).execute()

                logger.info(f"  {query}: {len(courses)} courses found")

            except Exception as e:
                logger.warning(f"  Error scraping Coursera for '{query}': {e}")

            await asyncio.sleep(0.5)

    logger.info(f"Coursera scraping complete: {total_syllabi} syllabi")
    return total_syllabi


async def scrape_edx(max_per_query: int = 20):
    """Scrape edX course catalog."""
    client = get_client()
    total_syllabi = 0

    async with httpx.AsyncClient(timeout=30) as http:
        for query in SEARCH_QUERIES:
            logger.info(f"Scraping edX: {query}")

            try:
                resp = await http.get(
                    EDX_CATALOG,
                    params={
                        "search_term": query,
                        "page_size": max_per_query,
                    },
                )

                if resp.status_code != 200:
                    # Try alternative edX discovery API
                    resp = await http.get(
                        "https://discovery.edx.org/api/v1/search/all/",
                        params={
                            "q": query,
                            "content_type": "course",
                            "page_size": max_per_query,
                        },
                    )

                if resp.status_code != 200:
                    logger.warning(f"  edX API returned {resp.status_code}")
                    continue

                data = resp.json()
                courses = data.get("results", data.get("objects", {}).get("results", []))

                for course in courses:
                    name = course.get("name") or course.get("title", "")
                    org = course.get("org") or course.get("organizations", ["edX"])[0] if isinstance(course.get("organizations"), list) else "edX"
                    description = course.get("short_description") or course.get("description", "")
                    course_id = course.get("course_id") or course.get("id", "")

                    if not name:
                        continue

                    url = f"https://www.edx.org/course/{course_id}" if course_id else ""

                    existing = (
                        client.table("syllabi")
                        .select("id")
                        .eq("title", name)
                        .eq("source", "edx")
                        .limit(1)
                        .execute()
                    )
                    if existing.data:
                        continue

                    department = query.replace("_", " ").title()
                    institution = org if isinstance(org, str) else str(org)

                    syllabus_data = {
                        "title": name,
                        "institution": f"edX ({institution})",
                        "department": department,
                        "url": url,
                        "source": "edx",
                        "is_template": True,
                    }

                    syl_result = client.table("syllabi").insert(syllabus_data).execute()
                    if syl_result.data:
                        total_syllabi += 1

                logger.info(f"  {query}: {len(courses)} courses found")

            except Exception as e:
                logger.warning(f"  Error scraping edX for '{query}': {e}")

            await asyncio.sleep(0.5)

    logger.info(f"edX scraping complete: {total_syllabi} syllabi")
    return total_syllabi


async def scrape_all():
    """Run both Coursera and edX scrapers."""
    c = await scrape_coursera()
    e = await scrape_edx()
    logger.info(f"Total: Coursera {c} + edX {e} = {c + e} syllabi")
    return c + e


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(scrape_all())
