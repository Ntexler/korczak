"""Generate field courses directly from the knowledge graph.

Instead of relying on scraped syllabi (which are mostly empty), this builds
structured courses from the papers and concepts we've already analyzed.

Logic:
- Foundation (Year 1): Concepts with highest paper_count = most established
- Core (Year 2): Theories, methods, frameworks
- Advanced (Year 3): Controversies, critiques, emerging concepts

Usage:
  python -m backend.pipeline.generate_field_courses --field Anthropology
  python -m backend.pipeline.generate_field_courses --all
"""

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timezone

from backend.config import settings
from backend.integrations.supabase_client import get_client

logger = logging.getLogger(__name__)

# Map field names to subfield patterns (must match _normalize_field in features.py)
FIELD_SUBFIELD_MAP = {
    "Anthropology": ["anthropol", "ethnograph", "archaeol", "decoloni", "indigenous", "settler", "postcoloni"],
    "Sleep & Cognition": ["sleep", "circadian", "wakefulness"],
    "Neuroscience": ["neurosci", "neuroph", "neuroimag", "neurodegen", "hippocamp", "neuroplast"],
    "Psychology": ["psychol", "psychomet"],
    "Sociology": ["sociol", "social theory", "social science"],
    "Economics": ["econom", "consumer"],
    "Political Science": ["politi", "international relation", "governance"],
    "Philosophy": ["philosoph", "phenomenol", "critical theory"],
    "Cognitive Science": ["cogniti", "consciousness"],
    "Medicine": ["medical", "clinical", "nephrol", "cardiol", "oncol", "hematol", "surg", "nurs",
                 "epidemiol", "hospital", "pharma", "anesthes", "perioper", "infect", "biomedic", "health"],
    "Climate Science": ["atmospheric", "climate", "meteorol", "ocean", "hydrolog"],
    "Geography": ["geograph", "urban", "spatial", "migration"],
    "Biology": ["biolog", "ecology", "ecosystem", "genetic"],
}


async def get_field_concepts(field: str) -> list[dict]:
    """Get all concepts belonging to a field, via paper_concepts → papers.subfield."""
    client = get_client()

    patterns = FIELD_SUBFIELD_MAP.get(field, [field.lower()])

    # Get papers matching this field
    all_papers = client.table("papers").select(
        "id, subfield, title, authors, publication_year, cited_by_count, abstract"
    ).not_.is_("subfield", "null").execute()

    field_papers = []
    for p in (all_papers.data or []):
        subfield = (p.get("subfield") or "").lower()
        if any(pat in subfield for pat in patterns):
            field_papers.append(p)

    if not field_papers:
        logger.warning(f"No papers found for {field}")
        return []

    logger.info(f"{field}: {len(field_papers)} papers found")

    # Get concept IDs for these papers
    paper_ids = [p["id"] for p in field_papers]
    concept_ids = set()
    for i in range(0, len(paper_ids), 50):
        batch = paper_ids[i:i+50]
        pc = client.table("paper_concepts").select(
            "concept_id, paper_id"
        ).in_("paper_id", batch).execute()
        for row in (pc.data or []):
            concept_ids.add(row["concept_id"])

    if not concept_ids:
        return []

    # Get full concept data — batch to avoid Supabase .in_() URL overflow
    # (the list can easily exceed 1000 IDs on large fields; PostgREST then
    # returns "JSON could not be generated / Bad Request")
    concept_id_list = list(concept_ids)
    all_concepts: list[dict] = []
    for i in range(0, len(concept_id_list), 100):
        batch = concept_id_list[i:i+100]
        res = client.table("concepts").select(
            "id, name, type, definition, paper_count, confidence, trend, controversy_score"
        ).in_("id", batch).execute()
        all_concepts.extend(res.data or [])

    # Sort by paper_count desc (so Foundation weeks pick most established concepts)
    all_concepts.sort(key=lambda c: c.get("paper_count", 0) or 0, reverse=True)

    # Cap at top 200 — Claude doesn't need all 40k, just the most established ones
    all_concepts = all_concepts[:200]

    logger.info(f"{field}: {len(all_concepts)} concepts found (top 200)")
    return all_concepts


async def generate_course_with_claude(
    field: str,
    concepts: list[dict],
    papers: list[dict],
    level: str = "intro",
) -> dict | None:
    """Use Claude to organize concepts into a structured course."""
    from backend.integrations.claude_client import _call_claude, _parse_json_response

    # Build concept summary
    concept_lines = []
    for i, c in enumerate(concepts[:50]):
        concept_lines.append(
            f"{i+1}. {c['name']} ({c.get('type', 'concept')}) — "
            f"{c.get('paper_count', 0)} papers, "
            f"confidence: {c.get('confidence', 0):.1f}"
            f"{', CONTROVERSIAL' if (c.get('controversy_score') or 0) > 0.5 else ''}"
        )

    # Build paper summary (top 20)
    paper_lines = []
    for p in papers[:20]:
        authors = ""
        if p.get("authors"):
            try:
                auth_list = json.loads(p["authors"]) if isinstance(p["authors"], str) else p["authors"]
                authors = auth_list[0].get("name", "") if auth_list else ""
            except (json.JSONDecodeError, TypeError):
                pass
        paper_lines.append(
            f"- \"{p['title']}\" ({p.get('publication_year', '?')}) by {authors}, "
            f"{p.get('cited_by_count', 0)} citations"
        )

    level_desc = {
        "intro": "Introduction (Year 1) — for students with no prior knowledge. Start from absolute basics.",
        "intermediate": "Intermediate (Year 2) — students know the foundations. Focus on theories and methods.",
        "advanced": "Advanced (Year 3) — students are ready for debates, critiques, and cutting-edge research.",
    }

    prompt = f"""You are a curriculum designer creating a {level_desc.get(level, 'intro')} course in {field}.

You have real academic data: {len(concepts)} concepts extracted from {len(papers)} peer-reviewed papers.

CONCEPTS (sorted by importance — most papers = most established):
{chr(10).join(concept_lines)}

KEY PAPERS:
{chr(10).join(paper_lines)}

Create a 14-week course. Return JSON:
{{
  "title": "Course title",
  "description": "2-3 sentence description",
  "weeks": [
    {{
      "week_number": 1,
      "title": "Week title (descriptive, not just 'Week 1')",
      "theme": "What students learn this week",
      "concepts": ["concept name 1", "concept name 2", "concept name 3"],
      "key_reading": "Most important paper title for this week",
      "learning_objectives": ["objective 1", "objective 2"]
    }}
  ]
}}

Rules:
1. Week 1-3: FOUNDATIONS — the most basic, established concepts everyone must know
2. Week 4-7: CORE THEORIES AND METHODS — major frameworks and research approaches
3. Week 8-10: APPLICATIONS AND CASE STUDIES — how theory meets practice
4. Week 11-13: DEBATES AND ADVANCED TOPICS — controversies, critiques, cutting edge
5. Week 14: SYNTHESIS — connecting everything, future directions
6. 2-4 concepts per week, each from the real concept list above
7. 1 key reading per week from the real paper list above
8. Learning objectives should be specific and measurable

Return ONLY valid JSON."""

    try:
        response = await _call_claude(
            prompt,
            model=settings.haiku_model,  # Cheap for course generation
            max_tokens=8000,  # Full 14-week course needs room; 2500 was truncating
            temperature=0.3,
        )

        parsed = _parse_json_response(response.text)
        if parsed.get("parse_error"):
            # Truncated or malformed JSON. Try to recover by extracting the
            # largest valid JSON object from the raw text (handles cases where
            # Claude added a preamble or the response hit max_tokens mid-week).
            import re
            raw = parsed.get("raw_text", "")
            logger.warning(
                f"Course for {field}/{level}: parse failed, attempting recovery. "
                f"Raw length: {len(raw)}, preview: {raw[:200]!r}"
            )
            # Strip code fences if present
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
                cleaned = re.sub(r"\s*```\s*$", "", cleaned)
            # Find the first `{` and try to parse from there, trimming any
            # trailing garbage / truncation character by character
            start = cleaned.find("{")
            if start >= 0:
                candidate = cleaned[start:]
                for end in range(len(candidate), start, -1):
                    try:
                        return json.loads(candidate[:end])
                    except json.JSONDecodeError:
                        continue
            logger.error(f"Course for {field}/{level}: could not recover valid JSON")
            return None

        return parsed
    except Exception as e:
        logger.error(f"Course generation failed for {field}/{level}: {e}")
        return None


async def generate_and_store_course(field: str, level: str = "intro"):
    """Generate a course and store it in the DB."""
    client = get_client()

    # Check if course already exists
    existing = client.table("generated_courses").select("id").eq(
        "department", field
    ).eq("level", level).execute()
    if existing.data:
        logger.info(f"Course already exists for {field}/{level}, skipping")
        return existing.data[0]["id"]

    # Get field data
    concepts = await get_field_concepts(field)
    if not concepts:
        logger.warning(f"No concepts for {field}, skipping")
        return None

    # Get papers
    patterns = FIELD_SUBFIELD_MAP.get(field, [field.lower()])
    all_papers = client.table("papers").select(
        "id, title, authors, publication_year, cited_by_count, abstract, subfield"
    ).not_.is_("subfield", "null").order("cited_by_count", desc=True).execute()

    field_papers = [
        p for p in (all_papers.data or [])
        if any(pat in (p.get("subfield") or "").lower() for pat in patterns)
    ]

    logger.info(f"Generating {field}/{level}: {len(concepts)} concepts, {len(field_papers)} papers")

    # Generate with Claude
    course_data = await generate_course_with_claude(field, concepts, field_papers, level)
    if not course_data:
        return None

    # Store in DB
    course_row = {
        "department": field,
        "level": level,
        "title": course_data.get("title", f"{field} — {level.title()}"),
        "description": course_data.get("description", ""),
        "methodology": f"Generated from {len(concepts)} concepts across {len(field_papers)} papers using AI curriculum design.",
        "weeks": json.dumps(course_data.get("weeks", [])),
        "source_syllabi_count": 0,
        "reading_count": sum(len(w.get("concepts", [])) for w in course_data.get("weeks", [])),
        "ai_recommendations_count": 0,
        "generated_model": settings.haiku_model,
        "is_published": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    result = client.table("generated_courses").insert(course_row).execute()
    if result.data:
        course_id = result.data[0]["id"]
        logger.info(f"Stored course: {course_data.get('title')} (id={course_id})")

        # Store individual readings
        for week in course_data.get("weeks", []):
            for i, concept_name in enumerate(week.get("concepts", [])):
                client.table("course_readings").insert({
                    "course_id": course_id,
                    "reading_title": concept_name,
                    "week": week.get("week_number", 1),
                    "position": i,
                    "section": "required",
                    "tier": "canonical" if week.get("week_number", 1) <= 3 else "important",
                    "rationale": week.get("theme", ""),
                }).execute()

        return course_id

    return None


async def generate_all():
    """Generate courses for all fields that have data."""
    fields_with_data = list(FIELD_SUBFIELD_MAP.keys())

    total = 0
    for field in fields_with_data:
        for level in ["intro", "intermediate", "advanced"]:
            result = await generate_and_store_course(field, level)
            if result:
                total += 1
                print(f"  {field}/{level}: OK")
            else:
                print(f"  {field}/{level}: skipped (no data)")

    print(f"\nGenerated {total} courses")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Generate courses from knowledge graph")
    parser.add_argument("--field", type=str, help="Field name")
    parser.add_argument("--level", type=str, default="intro", choices=["intro", "intermediate", "advanced"])
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()

    if args.all:
        asyncio.run(generate_all())
    elif args.field:
        result = asyncio.run(generate_and_store_course(args.field, args.level))
        print(f"Result: {result}")
    else:
        parser.error("Specify --field or --all")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
