"""OpenStax client — fetches free textbook catalog and chapter structures."""

import logging

import httpx

logger = logging.getLogger(__name__)

OPENSTAX_API = "https://openstax.org/apps/cms/api/v2"


async def fetch_books(limit: int = 100) -> list[dict]:
    """Fetch OpenStax book catalog.

    OpenStax provides free, peer-reviewed textbooks for college courses.
    """
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{OPENSTAX_API}/pages/",
                params={
                    "type": "books.Book",
                    "fields": "title,description,cover_url,subjects,publish_date",
                    "limit": limit,
                },
            )
            if response.status_code != 200:
                logger.warning(f"OpenStax API returned {response.status_code}")
                return []

            data = response.json()
            books = []
            for item in data.get("items", []):
                meta = item.get("meta", {})
                value = item.get("value", item)
                books.append({
                    "title": value.get("title", meta.get("title", "")),
                    "description": value.get("description", ""),
                    "url": f"https://openstax.org/details/books/{meta.get('slug', '')}",
                    "subjects": value.get("subjects", []),
                    "publish_date": value.get("publish_date"),
                    "source": "openstax",
                })
            return books
    except Exception as e:
        logger.error(f"OpenStax fetch error: {e}")
        return []


async def fetch_book_chapters(book_slug: str) -> list[dict]:
    """Fetch chapter structure for an OpenStax book.

    Returns [{title, chapter_number, sections: [{title, section_number}]}]
    """
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{OPENSTAX_API}/pages/",
                params={
                    "type": "books.Book",
                    "slug": book_slug,
                    "fields": "table_of_contents",
                },
            )
            if response.status_code != 200:
                return []

            data = response.json()
            items = data.get("items", [])
            if not items:
                return []

            toc = items[0].get("value", {}).get("table_of_contents", [])
            chapters = []
            for i, chapter in enumerate(toc):
                sections = []
                for j, section in enumerate(chapter.get("contents", [])):
                    sections.append({
                        "title": section.get("title", f"Section {j+1}"),
                        "section_number": j + 1,
                    })
                chapters.append({
                    "title": chapter.get("title", f"Chapter {i+1}"),
                    "chapter_number": i + 1,
                    "sections": sections,
                })
            return chapters
    except Exception as e:
        logger.error(f"OpenStax chapters error: {e}")
        return []
