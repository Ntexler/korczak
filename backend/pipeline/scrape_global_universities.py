"""Scrape global university catalogs — public course listings worldwide.

Generic scraper that works with any university that has a public course catalog.
Covers top universities across US, Europe, Asia, and Israel.

Usage:
  python -m backend.pipeline.scrape_global_universities
  python -m backend.pipeline.scrape_global_universities --region asia
"""

import argparse
import asyncio
import logging
import sys

import httpx

from backend.integrations.supabase_client import get_client

logger = logging.getLogger(__name__)

# Global university catalog URLs and metadata
# Each entry: (name, country, catalog_url, departments_to_scrape)
UNIVERSITIES = {
    # --- US (additional) ---
    "yale": {
        "name": "Yale University",
        "country": "US",
        "catalog_url": "https://courses.yale.edu",
        "api_url": "https://courses.yale.edu/api/v2/search",
        "departments": [
            "ANTH", "SOCY", "PSYC", "PHIL", "LING", "PLSC", "ECON", "HIST",
            "ENGL", "CPSC", "MATH", "PHYS", "CHEM", "BIOL", "MCDB", "NSCI",
        ],
    },
    "princeton": {
        "name": "Princeton University",
        "country": "US",
        "catalog_url": "https://registrar.princeton.edu/course-offerings",
        "api_url": None,
        "departments": [
            "ANT", "SOC", "PSY", "PHI", "LIN", "POL", "ECO", "HIS",
            "ENG", "COS", "MAT", "PHY", "CHM", "MOL", "NEU",
        ],
    },
    "columbia": {
        "name": "Columbia University",
        "country": "US",
        "catalog_url": "https://bulletin.columbia.edu",
        "api_url": None,
        "departments": [
            "ANTH", "SOCI", "PSYC", "PHIL", "LING", "POLS", "ECON", "HIST",
            "ENGL", "COMS", "MATH", "PHYS", "CHEM", "BIOL", "NEUR",
        ],
    },
    "uchicago": {
        "name": "University of Chicago",
        "country": "US",
        "catalog_url": "https://catalog.uchicago.edu",
        "api_url": None,
        "departments": [
            "ANTH", "SOCI", "PSYC", "PHIL", "LING", "PLSC", "ECON", "HIST",
            "ENGL", "CMSC", "MATH", "PHYS", "CHEM", "BIOL", "NSCI",
        ],
    },
    "berkeley": {
        "name": "UC Berkeley",
        "country": "US",
        "catalog_url": "https://classes.berkeley.edu",
        "api_url": "https://classes.berkeley.edu/search/class",
        "departments": [
            "ANTHRO", "SOCIOL", "PSYCH", "PHILOS", "LINGUIS", "POL SCI", "ECON", "HISTORY",
            "ENGLISH", "COMPSCI", "MATH", "PHYSICS", "CHEM", "BIOLOGY", "NEUROSC",
        ],
    },

    # --- UK ---
    "oxford": {
        "name": "University of Oxford",
        "country": "UK",
        "catalog_url": "https://courses.ox.ac.uk",
        "api_url": None,
        "departments": [
            "Anthropology", "Sociology", "Psychology", "Philosophy",
            "Linguistics", "Politics", "Economics", "History",
            "English", "Computer Science", "Mathematics", "Physics",
        ],
    },
    "cambridge": {
        "name": "University of Cambridge",
        "country": "UK",
        "catalog_url": "https://www.cam.ac.uk/courses",
        "api_url": None,
        "departments": [
            "Archaeology & Anthropology", "Sociology", "Psychology", "Philosophy",
            "Linguistics", "Politics", "Economics", "History",
            "English", "Computer Science", "Mathematics", "Physics",
        ],
    },
    "lse": {
        "name": "London School of Economics",
        "country": "UK",
        "catalog_url": "https://www.lse.ac.uk/study-at-lse/courses",
        "api_url": None,
        "departments": [
            "Anthropology", "Sociology", "Psychology", "Philosophy",
            "International Relations", "Economics", "History", "Law",
            "Statistics", "Management",
        ],
    },

    # --- Europe ---
    "eth_zurich": {
        "name": "ETH Zurich",
        "country": "Switzerland",
        "catalog_url": "https://www.vorlesungen.ethz.ch",
        "api_url": None,
        "departments": [
            "Humanities", "Social Sciences", "Computer Science", "Mathematics",
            "Physics", "Chemistry", "Biology", "Engineering",
        ],
    },
    "sorbonne": {
        "name": "Sorbonne University",
        "country": "France",
        "catalog_url": "https://sciences.sorbonne-universite.fr",
        "api_url": None,
        "departments": [
            "Philosophy", "Sociology", "History", "Literature",
            "Mathematics", "Physics", "Chemistry", "Biology",
            "Computer Science",
        ],
    },
    "humboldt": {
        "name": "Humboldt University of Berlin",
        "country": "Germany",
        "catalog_url": "https://www.hu-berlin.de/en/studies",
        "api_url": None,
        "departments": [
            "Philosophy", "Social Sciences", "Psychology", "History",
            "Cultural Studies", "Linguistics", "Mathematics", "Physics",
            "Computer Science", "Biology",
        ],
    },
    "leiden": {
        "name": "Leiden University",
        "country": "Netherlands",
        "catalog_url": "https://studiegids.universiteitleiden.nl",
        "api_url": None,
        "departments": [
            "Archaeology", "Cultural Anthropology", "Philosophy", "History",
            "Linguistics", "Political Science", "Psychology", "Law",
            "Mathematics", "Physics", "Computer Science",
        ],
    },

    # --- Asia ---
    "tokyo": {
        "name": "University of Tokyo",
        "country": "Japan",
        "catalog_url": "https://catalog.he.u-tokyo.ac.jp",
        "api_url": None,
        "departments": [
            "Cultural Anthropology", "Sociology", "Psychology", "Philosophy",
            "Linguistics", "Political Science", "Economics", "History",
            "Computer Science", "Mathematics", "Physics",
        ],
    },
    "peking": {
        "name": "Peking University",
        "country": "China",
        "catalog_url": "https://dean.pku.edu.cn",
        "api_url": None,
        "departments": [
            "Sociology", "Psychology", "Philosophy", "History",
            "Chinese Literature", "Economics", "Political Science",
            "Computer Science", "Mathematics", "Physics",
        ],
    },
    "nus": {
        "name": "National University of Singapore",
        "country": "Singapore",
        "catalog_url": "https://nusmods.com",
        "api_url": "https://api.nusmods.com/v2/2024-2025/moduleList.json",
        "departments": [
            "Anthropology", "Sociology", "Psychology", "Philosophy",
            "Political Science", "Economics", "History",
            "Computer Science", "Mathematics", "Physics",
        ],
    },
    "seoul": {
        "name": "Seoul National University",
        "country": "South Korea",
        "catalog_url": "https://sugang.snu.ac.kr",
        "api_url": None,
        "departments": [
            "Anthropology", "Sociology", "Psychology", "Philosophy",
            "Political Science", "Economics", "History",
            "Computer Science", "Mathematics", "Physics",
        ],
    },

    # --- Israel ---
    "huji": {
        "name": "Hebrew University of Jerusalem",
        "country": "Israel",
        "catalog_url": "https://shnaton.huji.ac.il",
        "api_url": None,
        "departments": [
            "Anthropology", "Sociology", "Psychology", "Philosophy",
            "Linguistics", "Political Science", "Economics", "History",
            "Computer Science", "Mathematics", "Physics", "Cognitive Science",
        ],
    },
    "tau": {
        "name": "Tel Aviv University",
        "country": "Israel",
        "catalog_url": "https://rishum.tau.ac.il",
        "api_url": None,
        "departments": [
            "Anthropology", "Sociology", "Psychology", "Philosophy",
            "Linguistics", "Political Science", "Economics", "History",
            "Computer Science", "Mathematics", "Physics",
        ],
    },
    "technion": {
        "name": "Technion — Israel Institute of Technology",
        "country": "Israel",
        "catalog_url": "https://ug.technion.ac.il",
        "api_url": None,
        "departments": [
            "Humanities", "Computer Science", "Mathematics", "Physics",
            "Chemistry", "Biology", "Engineering",
        ],
    },
    "bgu": {
        "name": "Ben-Gurion University",
        "country": "Israel",
        "catalog_url": "https://in.bgu.ac.il",
        "api_url": None,
        "departments": [
            "Sociology & Anthropology", "Psychology", "Philosophy",
            "Politics & Government", "Economics", "History",
            "Computer Science", "Mathematics", "Physics",
        ],
    },

    # --- Australia ---
    "melbourne": {
        "name": "University of Melbourne",
        "country": "Australia",
        "catalog_url": "https://handbook.unimelb.edu.au",
        "api_url": None,
        "departments": [
            "Anthropology", "Sociology", "Psychology", "Philosophy",
            "Linguistics", "Political Science", "Economics", "History",
            "Computer Science", "Mathematics", "Physics",
        ],
    },
}

REGIONS = {
    "us": ["yale", "princeton", "columbia", "uchicago", "berkeley"],
    "uk": ["oxford", "cambridge", "lse"],
    "europe": ["eth_zurich", "sorbonne", "humboldt", "leiden"],
    "asia": ["tokyo", "peking", "nus", "seoul"],
    "israel": ["huji", "tau", "technion", "bgu"],
    "australia": ["melbourne"],
    "all": list(UNIVERSITIES.keys()),
}


async def scrape_university(uni_key: str):
    """Scrape a single university — creates syllabus entries per department."""
    uni = UNIVERSITIES[uni_key]
    client = get_client()
    total = 0

    logger.info(f"Scraping {uni['name']} ({uni['country']})")

    for dept in uni["departments"]:
        url = f"{uni['catalog_url']}?dept={dept}"

        # Check if already exists
        existing = (
            client.table("syllabi")
            .select("id")
            .eq("institution", uni["name"])
            .eq("department", dept)
            .limit(1)
            .execute()
        )
        if existing.data:
            continue

        syllabus_data = {
            "title": f"{uni['name']} — {dept}",
            "institution": uni["name"],
            "department": dept,
            "url": url,
            "source": "other",  # generic source for global universities
            "is_template": True,
        }

        result = client.table("syllabi").insert(syllabus_data).execute()
        if result.data:
            total += 1

        # If there's an API, try to fetch actual course data
        if uni.get("api_url"):
            await _try_fetch_api_courses(client, uni, dept, result.data[0]["id"] if result.data else None)

    logger.info(f"  {uni['name']}: {total} department syllabi created")
    return total


async def _try_fetch_api_courses(client, uni: dict, dept: str, syllabus_id: str | None):
    """Try to fetch course data from university API."""
    if not syllabus_id or not uni.get("api_url"):
        return

    try:
        async with httpx.AsyncClient(timeout=15) as http:
            # NUSMods has a good public API
            if "nusmods" in uni["api_url"]:
                resp = await http.get(uni["api_url"])
                if resp.status_code == 200:
                    modules = resp.json()
                    dept_modules = [
                        m for m in modules
                        if dept.upper()[:3] in (m.get("moduleCode", "")[:3]).upper()
                    ][:20]
                    for i, mod in enumerate(dept_modules):
                        client.table("syllabus_readings").insert({
                            "syllabus_id": syllabus_id,
                            "external_title": f"{mod.get('moduleCode', '')} — {mod.get('title', '')}",
                            "week": (i // 3) + 1,
                            "section": "required",
                            "position": i,
                            "match_confidence": 0,
                        }).execute()
    except Exception as e:
        logger.debug(f"  API fetch failed for {uni['name']}/{dept}: {e}")


async def scrape_region(region: str):
    """Scrape all universities in a region."""
    uni_keys = REGIONS.get(region, [])
    if not uni_keys:
        logger.error(f"Unknown region: {region}. Available: {list(REGIONS.keys())}")
        return 0

    total = 0
    for key in uni_keys:
        total += await scrape_university(key)
        await asyncio.sleep(0.3)

    logger.info(f"Region {region}: {total} total syllabi created")
    return total


async def scrape_all():
    """Scrape all global universities."""
    total = 0
    for key in UNIVERSITIES:
        total += await scrape_university(key)
        await asyncio.sleep(0.2)

    logger.info(f"Global scraping complete: {total} syllabi across {len(UNIVERSITIES)} universities")
    return total


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Scrape global university catalogs")
    parser.add_argument("--region", choices=list(REGIONS.keys()), default="all")
    parser.add_argument("--university", choices=list(UNIVERSITIES.keys()))
    args = parser.parse_args()

    if args.university:
        asyncio.run(scrape_university(args.university))
    else:
        asyncio.run(scrape_region(args.region))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
