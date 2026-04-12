"""Scrape Stanford ExploreCourses — public course catalog with descriptions.

Stanford's ExploreCourses has a public XML/JSON interface.

Usage:
  python -m backend.pipeline.scrape_stanford
"""

import asyncio
import logging
import xml.etree.ElementTree as ET
import httpx

from backend.integrations.supabase_client import get_client

logger = logging.getLogger(__name__)

STANFORD_API = "https://explorecourses.stanford.edu/search"

# Departments to scrape
DEPARTMENTS = [
    ("ANTHRO", "Anthropology"), ("SOC", "Sociology"), ("PSYCH", "Psychology"),
    ("PHIL", "Philosophy"), ("LINGUIST", "Linguistics"), ("POLISCI", "Political Science"),
    ("ECON", "Economics"), ("HISTORY", "History"), ("ENGLISH", "English"),
    ("COMPLIT", "Comparative Literature"), ("CLASSICS", "Classics"),
    ("RELIGST", "Religious Studies"), ("FEMGEN", "Feminist, Gender & Sexuality Studies"),
    ("AFRICAST", "African & African American Studies"), ("CSRE", "Comparative Studies in Race & Ethnicity"),
    ("BIO", "Biology"), ("PHYSICS", "Physics"), ("CHEM", "Chemistry"),
    ("MATH", "Mathematics"), ("CS", "Computer Science"), ("STATS", "Statistics"),
    ("NEURO", "Neuroscience"), ("EARTHSYS", "Earth Systems"), ("EE", "Electrical Engineering"),
    ("ME", "Mechanical Engineering"), ("MS&E", "Management Science & Engineering"),
    ("EDUC", "Education"), ("COMM", "Communication"), ("MUSIC", "Music"),
    ("ARTSINST", "Arts Institute"), ("GLOBAL", "Global Studies"),
]


async def scrape_stanford(max_courses_per_dept: int = 30):
    """Scrape Stanford ExploreCourses for all departments."""
    client = get_client()
    total_syllabi = 0
    total_readings = 0

    async with httpx.AsyncClient(timeout=30) as http:
        for dept_code, dept_name in DEPARTMENTS:
            logger.info(f"Scraping Stanford: {dept_name} ({dept_code})")

            try:
                # Stanford ExploreCourses XML API
                resp = await http.get(
                    STANFORD_API,
                    params={
                        "view": "xml",
                        "filter-departmentcode-" + dept_code: "on",
                        "q": dept_code,
                        "page": 0,
                    },
                )

                courses = []
                if resp.status_code == 200 and "xml" in resp.headers.get("content-type", ""):
                    courses = _parse_stanford_xml(resp.text)
                elif resp.status_code == 200:
                    # Try JSON fallback
                    try:
                        data = resp.json()
                        courses = data.get("courses", [])
                    except Exception:
                        pass

                if not courses:
                    # Create placeholder
                    await _create_dept_placeholder(client, dept_code, dept_name)
                    total_syllabi += 1
                    continue

                for course in courses[:max_courses_per_dept]:
                    title = course.get("title", "")
                    description = course.get("description", "")
                    instructor = course.get("instructor", "")
                    units = course.get("units", "")
                    course_id = course.get("course_id", dept_code)

                    if not title:
                        continue

                    url = f"https://explorecourses.stanford.edu/search?q={dept_code}+{course_id}"

                    existing = (
                        client.table("syllabi")
                        .select("id")
                        .eq("title", title)
                        .eq("institution", "Stanford")
                        .limit(1)
                        .execute()
                    )
                    if existing.data:
                        continue

                    syllabus_data = {
                        "title": title,
                        "course_code": f"{dept_code} {course_id}",
                        "institution": "Stanford",
                        "department": dept_name,
                        "instructor": instructor[:200] if instructor else None,
                        "url": url,
                        "source": "stanford",
                        "is_template": True,
                    }

                    syl_result = client.table("syllabi").insert(syllabus_data).execute()
                    if syl_result.data:
                        total_syllabi += 1

                        # Store description as a reading note if substantial
                        if description and len(description) > 100:
                            syllabus_id = syl_result.data[0]["id"]
                            client.table("syllabus_readings").insert({
                                "syllabus_id": syllabus_id,
                                "external_title": f"Course description: {description[:300]}",
                                "week": 1,
                                "section": "supplementary",
                                "position": 0,
                                "match_confidence": 0,
                            }).execute()
                            total_readings += 1

                logger.info(f"  {dept_name}: processed")

            except Exception as e:
                logger.warning(f"  Error scraping {dept_name}: {e}")
                await _create_dept_placeholder(client, dept_code, dept_name)
                total_syllabi += 1

            await asyncio.sleep(0.5)

    logger.info(f"Stanford scraping complete: {total_syllabi} syllabi, {total_readings} readings")
    return total_syllabi, total_readings


def _parse_stanford_xml(xml_text: str) -> list[dict]:
    """Parse Stanford ExploreCourses XML response."""
    courses = []
    try:
        root = ET.fromstring(xml_text)
        for course_el in root.findall(".//course"):
            title = course_el.findtext("title", "")
            description = course_el.findtext("description", "")
            units_min = course_el.findtext("unitsMin", "")
            units_max = course_el.findtext("unitsMax", "")
            course_id = course_el.findtext("courseId", "")

            instructors = []
            for instr in course_el.findall(".//instructor"):
                name = instr.findtext("name", "")
                if name:
                    instructors.append(name)

            courses.append({
                "title": title,
                "description": description,
                "instructor": ", ".join(instructors),
                "units": f"{units_min}-{units_max}" if units_min else "",
                "course_id": course_id,
            })
    except ET.ParseError:
        pass
    return courses


async def _create_dept_placeholder(client, dept_code: str, dept_name: str):
    """Create a placeholder for a Stanford department."""
    url = f"https://explorecourses.stanford.edu/search?q={dept_code}"
    existing = (
        client.table("syllabi")
        .select("id")
        .eq("url", url)
        .limit(1)
        .execute()
    )
    if not existing.data:
        client.table("syllabi").insert({
            "title": f"Stanford {dept_name} — Course Catalog",
            "institution": "Stanford",
            "department": dept_name,
            "source": "stanford",
            "is_template": True,
            "url": url,
        }).execute()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(scrape_stanford())
