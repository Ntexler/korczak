"""MIT OCW client — fetches departments, courses, and readings from MIT OpenCourseWare."""

import logging
import re
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

MIT_OCW_API = "https://ocw.mit.edu/api/v0"
MIT_OCW_SEARCH = "https://ocw.mit.edu/search/"

# MIT OCW department codes and names
DEPARTMENTS = {
    "21A": "Anthropology",
    "9": "Brain and Cognitive Sciences",
    "17": "Political Science",
    "21H": "History",
    "21L": "Literature",
    "14": "Economics",
    "8": "Physics",
    "7": "Biology",
    "6": "Electrical Engineering and Computer Science",
    "18": "Mathematics",
    "24": "Linguistics and Philosophy",
    "11": "Urban Studies and Planning",
    "15": "Management",
    "22": "Nuclear Science and Engineering",
    "HST": "Health Sciences and Technology",
    "STS": "Science, Technology, and Society",
    "WGS": "Women's and Gender Studies",
    "CMS": "Comparative Media Studies",
    "21M": "Music and Theater Arts",
    "4": "Architecture",
    "10": "Chemical Engineering",
    "2": "Mechanical Engineering",
    "1": "Civil and Environmental Engineering",
    "3": "Materials Science and Engineering",
    "5": "Chemistry",
    "12": "Earth, Atmospheric, and Planetary Sciences",
    "16": "Aeronautics and Astronautics",
    "20": "Biological Engineering",
}


async def fetch_departments() -> list[dict]:
    """Get list of MIT OCW departments."""
    return [
        {"code": code, "name": name}
        for code, name in sorted(DEPARTMENTS.items(), key=lambda x: x[1])
    ]


async def fetch_courses(department: str, limit: int = 50) -> list[dict]:
    """Fetch courses for a department from MIT OCW.

    Uses the MIT OCW API to search for courses by department.
    """
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            # Try the search API
            params = {
                "department": department,
                "type": "course",
                "limit": limit,
            }
            response = await client.get(f"{MIT_OCW_API}/courses/", params=params)

            if response.status_code != 200:
                # Fallback: try scraping the department page
                return await _scrape_department_courses(department, limit)

            data = response.json()
            courses = []
            for item in data.get("results", []):
                courses.append({
                    "title": item.get("title", ""),
                    "course_code": item.get("course_id", ""),
                    "url": f"https://ocw.mit.edu{item.get('url', '')}",
                    "instructor": item.get("instructors", ""),
                    "year": item.get("year", None),
                    "department": DEPARTMENTS.get(department, department),
                })
            return courses
    except Exception as e:
        logger.error(f"MIT OCW fetch error: {e}")
        return []


async def _scrape_department_courses(department: str, limit: int) -> list[dict]:
    """Fallback scraping for MIT OCW course listings."""
    try:
        dept_name = DEPARTMENTS.get(department, department).lower().replace(" ", "-")
        url = f"https://ocw.mit.edu/courses/{department.lower()}-{dept_name}/"
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url)
            if response.status_code != 200:
                return []

            # Basic extraction from HTML
            courses = []
            # Look for course links in the HTML
            matches = re.findall(
                r'<a[^>]*href="(/courses/[^"]+)"[^>]*>([^<]+)</a>',
                response.text,
            )
            for href, title in matches[:limit]:
                if "/courses/" in href and title.strip():
                    courses.append({
                        "title": title.strip(),
                        "url": f"https://ocw.mit.edu{href}",
                        "department": DEPARTMENTS.get(department, department),
                    })
            return courses
    except Exception as e:
        logger.error(f"MIT OCW scrape error: {e}")
        return []


async def fetch_course_readings(course_url: str) -> list[dict]:
    """Fetch readings from a specific MIT OCW course page.

    Looks for the /readings or /syllabus page of a course.
    """
    try:
        readings = []
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            # Try readings page
            for path in ["/pages/readings/", "/pages/syllabus/", "/resources/"]:
                try:
                    url = course_url.rstrip("/") + path
                    response = await client.get(url)
                    if response.status_code == 200:
                        readings.extend(_extract_readings_from_html(response.text))
                        if readings:
                            break
                except Exception:
                    continue

        return readings
    except Exception as e:
        logger.error(f"Course readings error: {e}")
        return []


def _extract_readings_from_html(html: str) -> list[dict]:
    """Extract reading references from MIT OCW HTML pages."""
    readings = []

    # Look for citations (author, year, title patterns)
    citation_pattern = r'(?:(?P<authors>[A-Z][a-z]+(?:\s+(?:and|&)\s+[A-Z][a-z]+)?)\s*\((?P<year>\d{4})\)\s*[.,]?\s*["\u201c]?(?P<title>[^"\u201d\n]{10,200})["\u201d]?)'
    for match in re.finditer(citation_pattern, html):
        readings.append({
            "external_title": match.group("title").strip().rstrip("."),
            "external_authors": match.group("authors"),
            "external_year": int(match.group("year")),
        })

    # Look for DOIs
    doi_pattern = r'(?:doi[:\s]+|https?://doi\.org/)(\d+\.\d+/[^\s<"]+)'
    for match in re.finditer(doi_pattern, html, re.IGNORECASE):
        doi = match.group(1).rstrip(".")
        # Try to find associated title
        existing = [r for r in readings if not r.get("external_doi")]
        if existing:
            existing[-1]["external_doi"] = doi
        else:
            readings.append({"external_doi": doi})

    return readings


async def match_readings_to_papers(readings: list[dict]) -> list[dict]:
    """Match extracted readings against DB papers by DOI or title similarity.

    Returns readings with paper_id and match_confidence added.
    """
    from backend.integrations.supabase_client import get_client

    client = get_client()
    matched = []

    for reading in readings:
        paper_id = None
        confidence = 0.0

        # Try DOI match first (highest confidence)
        if reading.get("external_doi"):
            result = (
                client.table("papers")
                .select("id")
                .eq("doi", reading["external_doi"])
                .limit(1)
                .execute()
            )
            if result.data:
                paper_id = result.data[0]["id"]
                confidence = 1.0

        # Try title match
        if not paper_id and reading.get("external_title"):
            title = reading["external_title"]
            result = (
                client.table("papers")
                .select("id, title")
                .ilike("title", f"%{title[:50]}%")
                .limit(5)
                .execute()
            )
            if result.data:
                # Simple Levenshtein-like matching
                best = max(
                    result.data,
                    key=lambda p: _title_similarity(title, p.get("title", "")),
                )
                sim = _title_similarity(title, best.get("title", ""))
                if sim > 0.6:
                    paper_id = best["id"]
                    confidence = sim

        matched.append({
            **reading,
            "paper_id": paper_id,
            "match_confidence": confidence,
        })

    return matched


def _title_similarity(a: str, b: str) -> float:
    """Simple word-overlap similarity between two titles."""
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return 0.0
    overlap = words_a & words_b
    return len(overlap) / max(len(words_a), len(words_b))
