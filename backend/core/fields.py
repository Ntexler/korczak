"""Shared field taxonomy — single source of truth for paper→field mapping.

Extracted from api/features.py (audit: the substring map was imported and
re-run in 8 places, each wrapped in a full-table papers scan).

Fast path: query the persisted, indexed papers.field column (migration 027).
Fallback: legacy scan+normalize for rows seeded before the column existed.
Backfill: python -m backend.pipeline.backfill_fields
"""


def _normalize_field(subfield: str) -> str:
    """Map paper subfields to broader field names."""
    if not subfield:
        return ""
    s = subfield.lower()
    mappings = {
        "anthropol": "Anthropology", "ethnograph": "Anthropology", "ethnomusicol": "Anthropology",
        "archaeol": "Anthropology", "decoloni": "Anthropology", "indigenous": "Anthropology",
        "settler": "Anthropology", "postcoloni": "Anthropology",
        "sleep": "Sleep & Cognition", "circadian": "Sleep & Cognition", "wakefulness": "Sleep & Cognition",
        "cogniti": "Cognitive Science", "consciousness": "Cognitive Science",
        "psychol": "Psychology", "psychomet": "Psychology", "psycho-": "Psychology",
        "sociol": "Sociology", "social theory": "Sociology", "social science": "Sociology",
        "econom": "Economics", "consumer": "Economics",
        "politi": "Political Science", "international relation": "Political Science", "governance": "Political Science",
        "philosoph": "Philosophy", "phenomenol": "Philosophy", "critical theory": "Philosophy",
        "linguist": "Linguistics", "communication": "Linguistics",
        "histor": "History", "memory stud": "History", "heritage": "History", "slavery": "History",
        "biolog": "Biology", "ecology": "Biology", "ecosystem": "Biology", "genetic": "Biology",
        "neurosci": "Neuroscience", "neuroph": "Neuroscience", "neuroimag": "Neuroscience",
        "neurodegen": "Neuroscience", "hippocamp": "Neuroscience", "neuroplast": "Neuroscience",
        "physic": "Physics", "atmospheric": "Climate Science", "climate": "Climate Science",
        "meteorol": "Climate Science", "ocean": "Climate Science", "hydrolog": "Climate Science",
        "mathemat": "Mathematics", "statistic": "Mathematics", "computational": "Mathematics",
        "computer": "Computer Science", "digital": "Computer Science", "data stud": "Computer Science",
        "geograph": "Geography", "urban": "Geography", "spatial": "Geography", "migration": "Geography",
        "medical": "Medicine", "clinical": "Medicine", "nephrol": "Medicine", "cardiol": "Medicine",
        "oncol": "Medicine", "hematol": "Medicine", "surg": "Medicine", "nurs": "Medicine",
        "epidemiol": "Medicine", "hospital": "Medicine", "pharma": "Medicine", "anesthes": "Medicine",
        "perioper": "Medicine", "pain med": "Medicine", "infect": "Medicine", "diagnos": "Medicine",
        "dermatol": "Medicine", "pediatr": "Medicine", "geriatr": "Medicine", "psychiatr": "Medicine",
        "emergen": "Medicine", "integrative med": "Medicine", "critical care": "Medicine",
        "vascular": "Medicine", "biomedic": "Medicine", "health": "Medicine",
        "gender": "Gender Studies", "feminist": "Gender Studies", "queer": "Gender Studies", "women": "Gender Studies",
        "religio": "Religious Studies", "theolog": "Religious Studies",
        "legal": "Law", "law": "Law", "justice": "Law", "criminal": "Law",
        "education": "Education",
        "environment": "Environmental Science", "conservation": "Environmental Science",
        "media": "Media Studies", "visual": "Media Studies", "museum": "Media Studies",
        "tourism": "Cultural Studies", "cultural stud": "Cultural Studies", "food": "Cultural Studies",
        "african": "Area Studies", "asian": "Area Studies", "island": "Area Studies",
        "management": "Business", "organization": "Business", "marketing": "Business",
        "development": "Development Studies", "humanitarian": "Development Studies",
    }
    for key, field in mappings.items():
        if key in s:
            return field
    return ""  # Don't show unmapped subfields — they add noise


CORE_FIELDS = [
    "Anthropology", "Sleep & Cognition", "Cognitive Science", "Psychology",
    "Sociology", "Economics", "Political Science", "Philosophy", "Linguistics",
    "History", "Biology", "Neuroscience", "Physics", "Mathematics",
    "Computer Science", "Geography", "Medicine", "Climate Science",
    "Gender Studies", "Religious Studies", "Law", "Education",
    "Environmental Science", "Media Studies", "Cultural Studies",
    "Area Studies", "Business", "Development Studies",
]


def normalize_field(subfield: str) -> str:
    """Public name for the mapper."""
    return _normalize_field(subfield)


def get_field_paper_ids(client, field_name: str) -> list[str]:
    """All paper ids for a field. Indexed-column fast path, legacy fallback.

    Replaces the 7-site "fetch ALL papers, filter in Python" pattern.
    """
    try:
        fast = client.table("papers").select("id").eq("field", field_name).execute()
        if fast.data:
            return [p["id"] for p in fast.data]
    except Exception:
        pass  # column may not exist yet (migration not run)

    # Legacy fallback: full scan + substring map (pre-backfill rows)
    all_papers = client.table("papers").select("id, subfield").not_.is_(
        "subfield", "null"
    ).execute()
    return [
        p["id"] for p in (all_papers.data or [])
        if _normalize_field(p.get("subfield", "")) == field_name
    ]
