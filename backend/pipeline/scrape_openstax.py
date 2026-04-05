"""Scrape OpenStax — fetches free textbook catalog and creates syllabus records."""

import asyncio
import logging

from backend.integrations.openstax_client import fetch_books, fetch_book_chapters
from backend.integrations.supabase_client import get_client

logger = logging.getLogger(__name__)


async def scrape_openstax_catalog():
    """Scrape all OpenStax textbooks and create syllabus records.

    OpenStax provides free, peer-reviewed textbooks for introductory college courses.
    """
    client = get_client()
    books = await fetch_books()
    total = 0

    for book in books:
        try:
            url = book.get("url", "")

            # Check if already exists
            existing = (
                client.table("syllabi")
                .select("id")
                .eq("url", url)
                .limit(1)
                .execute()
            )
            if existing.data:
                continue

            # Map subjects to department
            subjects = book.get("subjects", [])
            department = _map_subjects_to_department(subjects)

            syllabus_data = {
                "title": book.get("title", ""),
                "institution": "OpenStax",
                "department": department,
                "url": url,
                "source": "openstax",
                "license": "CC BY 4.0",
                "is_template": True,
            }

            result = client.table("syllabi").insert(syllabus_data).execute()
            if not result.data:
                continue
            syllabus_id = result.data[0]["id"]
            total += 1

            # Fetch chapters and create readings for chapter structure
            slug = url.split("/books/")[-1] if "/books/" in url else ""
            if slug:
                chapters = await fetch_book_chapters(slug)
                reading_count = 0
                for chapter in chapters:
                    reading_data = {
                        "syllabus_id": syllabus_id,
                        "external_title": chapter.get("title", ""),
                        "week": chapter.get("chapter_number", 0),
                        "section": "required",
                        "position": chapter.get("chapter_number", 0),
                        "match_confidence": 0,
                    }
                    client.table("syllabus_readings").insert(reading_data).execute()
                    reading_count += 1

                # Update paper_count
                client.table("syllabi").update(
                    {"paper_count": reading_count}
                ).eq("id", syllabus_id).execute()

            logger.info(f"Added: {book['title']} ({department})")
            await asyncio.sleep(0.5)

        except Exception as e:
            logger.error(f"Error processing {book.get('title', '?')}: {e}")
            continue

    logger.info(f"OpenStax scraping complete: {total} textbooks")
    return {"textbooks": total}


def _map_subjects_to_department(subjects: list) -> str:
    """Map OpenStax subject tags to department names."""
    subject_map = {
        "Math": "Mathematics",
        "Science": "Science",
        "Social Sciences": "Social Sciences",
        "Humanities": "Humanities",
        "Business": "Business",
        "Biology": "Biology",
        "Chemistry": "Chemistry",
        "Physics": "Physics",
        "Economics": "Economics",
        "Psychology": "Psychology",
        "Sociology": "Sociology",
        "Statistics": "Statistics",
        "Anatomy": "Biology",
        "Astronomy": "Physics",
        "Accounting": "Business",
    }
    for s in subjects:
        if isinstance(s, dict):
            s = s.get("name", "")
        if s in subject_map:
            return subject_map[s]
    return "General"
