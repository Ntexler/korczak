"""Syllabus Analyzer — generates optimal courses from cross-syllabus analysis.

Uses reading scores + AI curation to produce structured week-by-week courses.

Usage:
  python -m backend.pipeline.syllabus_analyzer --department Anthropology --level intro
  python -m backend.pipeline.syllabus_analyzer --all
"""

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timezone

from backend.config import settings
from backend.integrations.claude_client import _call_claude, _parse_json_response
from backend.integrations.supabase_client import get_client

logger = logging.getLogger(__name__)


async def analyze_department(department: str) -> dict:
    """Analyze a department's syllabus landscape."""
    client = get_client()

    # Get all syllabi for this department
    syllabi = client.table("syllabi").select(
        "id, institution, source"
    ).eq("department", department).execute()

    # Get reading scores
    scores = client.table("reading_scores").select("*").eq(
        "department", department
    ).order("combined_score", desc=True).execute()

    if not scores.data:
        return {"department": department, "total_syllabi": 0, "message": "No scored readings"}

    # Count tiers
    tier_counts = {}
    for s in scores.data:
        tier = s.get("tier", "niche")
        tier_counts[tier] = tier_counts.get(tier, 0) + 1

    # Source breakdown
    source_counts = {}
    for s in (syllabi.data or []):
        src = s.get("source", "unknown")
        source_counts[src] = source_counts.get(src, 0) + 1

    return {
        "department": department,
        "total_syllabi": len(syllabi.data) if syllabi.data else 0,
        "source_breakdown": source_counts,
        "canonical_count": tier_counts.get("canonical", 0),
        "important_count": tier_counts.get("important", 0),
        "specialized_count": tier_counts.get("specialized", 0),
        "niche_count": tier_counts.get("niche", 0),
        "ai_recommended_count": tier_counts.get("ai_recommended", 0),
        "total_scored_readings": len(scores.data),
        "top_10": [
            {"title": s["reading_title"], "score": s["combined_score"], "tier": s["tier"]}
            for s in scores.data[:10]
        ],
    }


async def generate_course(
    department: str,
    level: str = "intro",
    weeks: int = 14,
) -> dict | None:
    """Generate an optimal course from scored readings.

    Args:
        department: Academic department name
        level: intro, intermediate, advanced, or graduate
        weeks: Number of weeks in the course (default 14)
    """
    client = get_client()

    # 1. Get scored readings for this department
    scores = client.table("reading_scores").select("*").eq(
        "department", department
    ).order("combined_score", desc=True).execute()

    if not scores.data:
        logger.warning(f"No scored readings for {department}")
        return None

    # 2. Filter by level
    if level == "intro":
        # Top readings by combined score — canonical + important
        readings = [s for s in scores.data if s["tier"] in ("canonical", "important")][:40]
    elif level == "intermediate":
        # Mix of important + specialized
        readings = [s for s in scores.data if s["tier"] in ("important", "specialized")][:40]
    elif level == "advanced":
        # Specialized + AI-recommended
        readings = [s for s in scores.data if s["tier"] in ("specialized", "ai_recommended")][:40]
    else:  # graduate
        # Everything including niche
        readings = scores.data[:50]

    # Always include a few AI-recommended "hidden gems"
    ai_recs = [s for s in scores.data if s["tier"] == "ai_recommended"][:5]
    reading_titles_set = {r["reading_title"] for r in readings}
    for rec in ai_recs:
        if rec["reading_title"] not in reading_titles_set:
            readings.append(rec)

    if not readings:
        logger.warning(f"No readings after filtering for {department}/{level}")
        return None

    # 3. Build reading summaries for Claude
    reading_lines = []
    for i, r in enumerate(readings):
        tier_label = r["tier"].upper()
        authors = r.get("authors", "")[:50]
        year = r.get("publication_year", "")
        score = r.get("combined_score", 0)
        rationale = r.get("ai_rationale", "")

        line = f"{i+1}. [{tier_label}] \"{r['reading_title']}\" — {authors} ({year}), score={score:.2f}"
        if rationale:
            line += f" | AI note: {rationale[:100]}"
        reading_lines.append(line)

    # 4. Ask Claude to organize into a course
    prompt = f"""You are a curriculum designer creating an optimal {level}-level university course in {department}.

You have {len(readings)} readings ranked by a cross-institutional analysis of syllabi from MIT, Harvard, Stanford, Coursera, edX, and the Open Syllabus Project. Each reading has a tier:
- CANONICAL: appears in >60% of syllabi across 3+ institutions
- IMPORTANT: appears in 30-60% of syllabi
- SPECIALIZED: appears in 10-30% of syllabi
- AI_RECOMMENDED: niche but conceptually important (Korczak's recommendation)

Organize these into a {weeks}-week course. Return JSON:
{{
  "title": "Course title",
  "description": "2-3 sentence course description",
  "weeks": [
    {{
      "week_number": 1,
      "title": "Week title",
      "learning_objectives": ["objective 1", "objective 2"],
      "required_readings": [
        {{"index": 1, "rationale": "Why this reading this week"}}
      ],
      "recommended_readings": [
        {{"index": 5, "rationale": "For deeper exploration"}}
      ]
    }}
  ]
}}

Rules:
1. Foundational/canonical readings in early weeks
2. Build complexity progressively
3. Include 1-2 AI_RECOMMENDED readings per course with clear rationale
4. Balance theory + methodology + case studies per week
5. 2-3 required readings per week, 1-2 recommended
6. Each reading used at most once across all weeks

Available readings:
{chr(10).join(reading_lines)}

Return ONLY valid JSON.
"""

    try:
        response = await _call_claude(
            prompt,
            model=settings.sonnet_model,
            max_tokens=2500,
            temperature=0.3,
        )
        parsed = _parse_json_response(response.text)

        if parsed.get("parse_error"):
            logger.error("Failed to parse course generation response")
            return None

        # 5. Store in DB
        course_data = {
            "department": department,
            "level": level,
            "title": parsed.get("title", f"{department} — {level.title()}"),
            "description": parsed.get("description", ""),
            "methodology": (
                f"Generated from {len(readings)} readings scored across syllabi from "
                f"MIT, Harvard, Stanford, Coursera, edX, and Open Syllabus Project. "
                f"Includes AI-curated readings for conceptual completeness."
            ),
            "weeks": json.dumps(parsed.get("weeks", [])),
            "source_syllabi_count": len(set(
                inst for r in readings for inst in (r.get("source_institutions") or [])
            )),
            "reading_count": len(readings),
            "ai_recommendations_count": len([r for r in readings if r["tier"] == "ai_recommended"]),
            "generated_model": settings.sonnet_model,
            "is_published": True,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

        result = client.table("generated_courses").insert(course_data).execute()
        if not result.data:
            logger.error("Failed to insert generated course")
            return None

        course_id = result.data[0]["id"]

        # 6. Insert course readings with rationale
        for week_data in parsed.get("weeks", []):
            week_num = week_data.get("week_number", 1)
            pos = 0
            for section_key, section_name in [
                ("required_readings", "required"),
                ("recommended_readings", "recommended"),
            ]:
                for reading_ref in week_data.get(section_key, []):
                    idx = reading_ref.get("index", 1) - 1
                    if 0 <= idx < len(readings):
                        r = readings[idx]
                        client.table("course_readings").insert({
                            "course_id": course_id,
                            "paper_id": r.get("paper_id"),
                            "reading_title": r["reading_title"][:500],
                            "week": week_num,
                            "position": pos,
                            "section": section_name,
                            "combined_score": r.get("combined_score", 0),
                            "tier": r.get("tier", "niche"),
                            "rationale": reading_ref.get("rationale", ""),
                            "is_ai_recommended": r.get("tier") == "ai_recommended",
                        }).execute()
                        pos += 1

        logger.info(
            f"Generated course: {parsed.get('title')} "
            f"({len(parsed.get('weeks', []))} weeks, {len(readings)} readings)"
        )
        return {**course_data, "id": course_id}

    except Exception as e:
        logger.error(f"Course generation failed: {e}")
        return None


async def generate_all_courses():
    """Generate courses for all departments that have scored readings."""
    client = get_client()

    # Get departments with readings
    dept_result = client.table("reading_scores").select("department").execute()
    departments = list(set(r["department"] for r in dept_result.data)) if dept_result.data else []

    if not departments:
        logger.warning("No departments with scored readings")
        return

    logger.info(f"Generating courses for {len(departments)} departments")

    for dept in sorted(departments):
        for level in ["intro", "intermediate", "advanced", "graduate"]:
            logger.info(f"Generating {dept} / {level}...")
            await generate_course(dept, level)

    logger.info("All courses generated")


def main():
    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Generate courses from syllabus analysis")
    parser.add_argument("--department", type=str, help="Department to analyze")
    parser.add_argument("--level", type=str, default="intro",
                        choices=["intro", "intermediate", "advanced", "graduate"])
    parser.add_argument("--all", action="store_true", help="Generate for all departments")
    parser.add_argument("--analyze-only", action="store_true", help="Only analyze, don't generate")
    args = parser.parse_args()

    if args.all:
        asyncio.run(generate_all_courses())
    elif args.department:
        if args.analyze_only:
            result = asyncio.run(analyze_department(args.department))
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            result = asyncio.run(generate_course(args.department, args.level))
            if result:
                print(f"Generated: {result.get('title')}")
            else:
                print("No course generated — check if reading scores exist")
    else:
        parser.error("Specify --department or --all")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
