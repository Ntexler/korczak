"""Scrape Harvard course catalog — public course listings with descriptions.

Uses Harvard's public course catalog API to extract course information
across all departments.

Usage:
  python -m backend.pipeline.scrape_harvard
"""

import asyncio
import logging
import re
import httpx

from backend.integrations.supabase_client import get_client

logger = logging.getLogger(__name__)

# Harvard's public course catalog
HARVARD_API = "https://courses.my.harvard.edu/psp/courses/EMPLOYEE/EMPL/h/"
HARVARD_SEARCH = "https://portal.my.harvard.edu/api/v1/courses"

# Departments to scrape
DEPARTMENTS = [
    "ANTHRO", "SOC", "PSY", "PHIL", "LING", "GOV", "ECON", "HIST",
    "AFRAMER", "COMPLIT", "EAS", "MES", "SAS", "MUSIC", "VES",
    "GENED", "EXPOS", "FRSEMR", "WOMGEN", "REL", "CLASARCH",
    "MCB", "OEB", "NEURO", "PHYS", "CHEM", "MATH", "COMPSCI",
    "STAT", "APMTH", "EPS", "ASTRON", "ENGSC",
]

DEPT_NAMES = {
    "ANTHRO": "Anthropology", "SOC": "Sociology", "PSY": "Psychology",
    "PHIL": "Philosophy", "LING": "Linguistics", "GOV": "Government",
    "ECON": "Economics", "HIST": "History", "AFRAMER": "African American Studies",
    "COMPLIT": "Comparative Literature", "EAS": "East Asian Studies",
    "MES": "Middle Eastern Studies", "SAS": "South Asian Studies",
    "MUSIC": "Music", "VES": "Visual & Environmental Studies",
    "GENED": "General Education", "EXPOS": "Expository Writing",
    "FRSEMR": "Freshman Seminars", "WOMGEN": "Women & Gender Studies",
    "REL": "Religion", "CLASARCH": "Classical Archaeology",
    "MCB": "Molecular & Cellular Biology", "OEB": "Organismic & Evolutionary Biology",
    "NEURO": "Neuroscience", "PHYS": "Physics", "CHEM": "Chemistry",
    "MATH": "Mathematics", "COMPSCI": "Computer Science",
    "STAT": "Statistics", "APMTH": "Applied Mathematics",
    "EPS": "Earth & Planetary Sciences", "ASTRON": "Astronomy", "ENGSC": "Engineering Sciences",
}


async def scrape_harvard(max_courses_per_dept: int = 30):
    """Scrape Harvard course catalog and extract course info."""
    client = get_client()
    total_syllabi = 0
    total_readings = 0

    async with httpx.AsyncClient(timeout=30) as http:
        for dept_code in DEPARTMENTS:
            dept_name = DEPT_NAMES.get(dept_code, dept_code)
            logger.info(f"Scraping Harvard: {dept_name} ({dept_code})")

            try:
                # Try Harvard's public course search
                resp = await http.get(
                    f"https://courses.my.harvard.edu/psp/courses/EMPLOYEE/EMPL/h/?tab=DEFAULT&SearchReqJSON="
                    f'{{"PageNumber":1,"PageSize":{max_courses_per_dept},'
                    f'"SortOrder":["IS_SCL_DESCR100"],'
                    f'"Facets":[],"Category":"HU_SCL_SCHEDULED_BRACKETED_COURSES",'
                    f'"SearchPropertiesIn498":{{"IS_SCL_SUBJ_CAT":"{dept_code}"}}}}',
                    headers={"Accept": "application/json"},
                )

                courses = []
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                        courses = data.get("ResultsCollection", data.get("results", []))
                    except Exception:
                        pass

                if not courses:
                    # Fallback: create department placeholder with known course patterns
                    await _create_dept_courses(client, dept_code, dept_name)
                    total_syllabi += 1
                    continue

                for course in courses[:max_courses_per_dept]:
                    title = course.get("Title") or course.get("title", "")
                    description = course.get("Description") or course.get("description", "")
                    instructor = course.get("Instructor") or course.get("instructor", "")
                    course_code = course.get("CourseCode") or course.get("code", f"{dept_code}")
                    url = course.get("URL") or f"https://courses.my.harvard.edu/?q={dept_code}"

                    if not title:
                        continue

                    # Check if already exists
                    existing = (
                        client.table("syllabi")
                        .select("id")
                        .eq("title", title)
                        .eq("institution", "Harvard")
                        .limit(1)
                        .execute()
                    )
                    if existing.data:
                        continue

                    syllabus_data = {
                        "title": title,
                        "course_code": course_code,
                        "institution": "Harvard",
                        "department": dept_name,
                        "instructor": instructor[:200] if instructor else None,
                        "url": url,
                        "source": "harvard",
                        "is_template": True,
                    }

                    syl_result = client.table("syllabi").insert(syllabus_data).execute()
                    if syl_result.data:
                        total_syllabi += 1

                        # Extract readings from description if available
                        if description:
                            readings = _extract_readings_from_description(description)
                            syllabus_id = syl_result.data[0]["id"]
                            for i, reading in enumerate(readings):
                                reading_data = {
                                    "syllabus_id": syllabus_id,
                                    "external_title": reading[:500],
                                    "week": (i // 3) + 1,
                                    "section": "required",
                                    "position": i,
                                    "match_confidence": 0,
                                }
                                client.table("syllabus_readings").insert(reading_data).execute()
                                total_readings += 1

                logger.info(f"  {dept_name}: {total_syllabi} courses")

            except Exception as e:
                logger.warning(f"  Error scraping {dept_name}: {e}")
                await _create_dept_courses(client, dept_code, dept_name)
                total_syllabi += 1

            await asyncio.sleep(0.5)

    logger.info(f"Harvard scraping complete: {total_syllabi} syllabi, {total_readings} readings")
    return total_syllabi, total_readings


def _extract_readings_from_description(description: str) -> list[str]:
    """Extract potential reading titles from course descriptions."""
    readings = []
    # Look for patterns like "Author (Year)" or "Title by Author"
    patterns = [
        r'(?:read|text|book|work)s?\s*(?:include|:)\s*(.+?)(?:\.|;|$)',
        r'"([^"]{10,100})"',  # Quoted titles
        r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s*\(\d{4}\)',  # Author (Year)
    ]
    for pattern in patterns:
        matches = re.findall(pattern, description, re.IGNORECASE)
        readings.extend(matches)
    return readings[:20]


async def _create_dept_courses(client, dept_code: str, dept_name: str):
    """Create a placeholder for a Harvard department."""
    syllabus_data = {
        "title": f"Harvard {dept_name} — Course Catalog",
        "institution": "Harvard",
        "department": dept_name,
        "source": "harvard",
        "is_template": True,
        "url": f"https://courses.my.harvard.edu/?q={dept_code}",
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
    asyncio.run(scrape_harvard())
