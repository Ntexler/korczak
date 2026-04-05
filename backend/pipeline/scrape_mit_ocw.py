"""Scrape MIT OCW — iterates all departments, fetches courses and readings."""

import asyncio
import logging

from backend.integrations.mit_ocw_client import (
    fetch_departments,
    fetch_courses,
    fetch_course_readings,
    match_readings_to_papers,
    DEPARTMENTS,
)
from backend.integrations.supabase_client import get_client

logger = logging.getLogger(__name__)


async def scrape_all_departments(max_courses_per_dept: int = 20):
    """Scrape all MIT OCW departments, create syllabi and readings in DB.

    This is a pipeline script — run manually or via scheduler.
    """
    client = get_client()
    departments = await fetch_departments()
    total_syllabi = 0
    total_readings = 0

    for dept in departments:
        code = dept["code"]
        name = dept["name"]
        logger.info(f"Scraping MIT OCW department: {name} ({code})")

        courses = await fetch_courses(code, limit=max_courses_per_dept)
        if not courses:
            logger.info(f"  No courses found for {name}")
            continue

        for course in courses:
            try:
                # Create syllabus record
                syllabus_data = {
                    "title": course.get("title", ""),
                    "course_code": course.get("course_code", ""),
                    "institution": "MIT",
                    "department": name,
                    "instructor": course.get("instructor", ""),
                    "year": course.get("year"),
                    "url": course.get("url", ""),
                    "source": "mit_ocw",
                    "is_template": True,
                }

                # Check if already exists
                existing = (
                    client.table("syllabi")
                    .select("id")
                    .eq("url", course.get("url", ""))
                    .limit(1)
                    .execute()
                )
                if existing.data:
                    logger.info(f"  Skipping (exists): {course['title']}")
                    continue

                result = client.table("syllabi").insert(syllabus_data).execute()
                if not result.data:
                    continue
                syllabus_id = result.data[0]["id"]
                total_syllabi += 1

                # Fetch readings
                readings = await fetch_course_readings(course.get("url", ""))
                if not readings:
                    continue

                # Match to DB papers
                matched = await match_readings_to_papers(readings)

                # Insert readings
                for i, reading in enumerate(matched):
                    reading_data = {
                        "syllabus_id": syllabus_id,
                        "paper_id": reading.get("paper_id"),
                        "external_title": reading.get("external_title", ""),
                        "external_authors": reading.get("external_authors", ""),
                        "external_year": reading.get("external_year"),
                        "external_doi": reading.get("external_doi"),
                        "week": (i // 3) + 1,  # Rough week assignment
                        "section": "required",
                        "position": i,
                        "match_confidence": reading.get("match_confidence", 0),
                    }
                    client.table("syllabus_readings").insert(reading_data).execute()
                    total_readings += 1

                # Update paper_count
                client.table("syllabi").update(
                    {"paper_count": len(matched)}
                ).eq("id", syllabus_id).execute()

                logger.info(f"  Added: {course['title']} ({len(matched)} readings)")

                # Rate limiting
                await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"  Error processing {course.get('title', '?')}: {e}")
                continue

        # Rate limiting between departments
        await asyncio.sleep(2)

    logger.info(f"MIT OCW scraping complete: {total_syllabi} syllabi, {total_readings} readings")
    return {"syllabi": total_syllabi, "readings": total_readings}


async def scrape_department(department_code: str, max_courses: int = 50):
    """Scrape a single MIT OCW department."""
    name = DEPARTMENTS.get(department_code, department_code)
    logger.info(f"Scraping department: {name}")
    courses = await fetch_courses(department_code, limit=max_courses)
    # Same logic as above for a single department
    client = get_client()
    count = 0
    for course in courses:
        try:
            existing = (
                client.table("syllabi")
                .select("id")
                .eq("url", course.get("url", ""))
                .limit(1)
                .execute()
            )
            if existing.data:
                continue

            result = client.table("syllabi").insert({
                "title": course.get("title", ""),
                "course_code": course.get("course_code", ""),
                "institution": "MIT",
                "department": name,
                "url": course.get("url", ""),
                "source": "mit_ocw",
                "is_template": True,
            }).execute()
            if result.data:
                count += 1
            await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Error: {e}")

    logger.info(f"Added {count} courses from {name}")
    return count
