"""Reading Scorer — computes cross-syllabus scores for all readings.

Pure computation, no AI calls. Runs after scrapers populate data.
Combines frequency, institutional diversity, citation weight, teaching score,
and user feedback into a single combined_score per reading.
"""

import logging
import math
from collections import defaultdict
from datetime import datetime, timezone

from backend.integrations.supabase_client import get_client
from backend.pipeline.syllabus_models import ReadingTier, USER_ADJUSTMENT_CAP, CANONICAL_SCORE_FLOOR

logger = logging.getLogger(__name__)

# Score weights
W_FREQUENCY = 0.35
W_INSTITUTION = 0.20
W_CITATION = 0.15
W_TEACHING = 0.15
W_POSITION = 0.10
W_USER = 0.05


def score_all_readings():
    """Compute and store scores for all readings across all departments.

    Groups readings by normalized title, computes metrics, classifies tier,
    and upserts into reading_scores table.
    """
    client = get_client()

    # 1. Fetch all syllabi with their institution/department
    syllabi_result = client.table("syllabi").select(
        "id, institution, department, source"
    ).eq("is_template", True).execute()
    syllabi = {s["id"]: s for s in syllabi_result.data}

    if not syllabi:
        logger.warning("No syllabi found in DB")
        return 0

    # 2. Fetch all readings
    readings_result = client.table("syllabus_readings").select(
        "id, syllabus_id, paper_id, external_title, external_authors, "
        "external_year, week, section, match_confidence"
    ).execute()
    all_readings = readings_result.data

    if not all_readings:
        logger.warning("No readings found in DB")
        return 0

    # 3. Group readings by normalized title
    title_groups = defaultdict(list)
    for r in all_readings:
        title = _normalize_title(r.get("external_title") or "")
        if len(title) < 5:
            continue
        title_groups[title].append(r)

    # 4. Get department → total syllabi count
    dept_syllabi_count = defaultdict(int)
    for s in syllabi.values():
        dept = s.get("department", "Unknown")
        dept_syllabi_count[dept] += 1

    # 5. Fetch citation counts for linked papers
    paper_ids = set()
    for readings in title_groups.values():
        for r in readings:
            if r.get("paper_id"):
                paper_ids.add(r["paper_id"])

    paper_citations = {}
    if paper_ids:
        papers_result = client.table("papers").select(
            "id, cited_by_count"
        ).in_("id", list(paper_ids)).execute()
        paper_citations = {p["id"]: p.get("cited_by_count", 0) for p in papers_result.data}

    # 6. Fetch user feedback
    feedback_result = client.table("reading_feedback").select(
        "course_reading_id, vote_type, vote_weight, is_suspicious"
    ).eq("is_suspicious", False).execute()
    # We'll apply this later when course_readings exist

    # 7. Compute scores per title group
    max_citations = max(paper_citations.values()) if paper_citations else 1
    scored_readings = []

    for title, readings in title_groups.items():
        # Determine departments this reading appears in
        departments = set()
        institutions = set()
        weeks = []
        paper_id = None
        authors = ""
        pub_year = None

        for r in readings:
            syl = syllabi.get(r["syllabus_id"])
            if syl:
                departments.add(syl.get("department", "Unknown"))
                institutions.add(syl.get("institution", "Unknown"))
            if r.get("week"):
                weeks.append(r["week"])
            if r.get("paper_id") and not paper_id:
                paper_id = r["paper_id"]
            if r.get("external_authors") and not authors:
                authors = r["external_authors"]
            if r.get("external_year") and not pub_year:
                pub_year = r["external_year"]

        # Score for each department this reading appears in
        for dept in departments:
            dept_readings = [
                r for r in readings
                if syllabi.get(r["syllabus_id"], {}).get("department") == dept
            ]
            dept_total = max(dept_syllabi_count.get(dept, 1), 1)

            # Frequency: how many syllabi in this dept include it
            frequency = len(dept_readings) / dept_total

            # Institution diversity: unique institutions / max possible
            dept_institutions = set()
            for r in dept_readings:
                syl = syllabi.get(r["syllabus_id"])
                if syl:
                    dept_institutions.add(syl.get("institution", ""))
            inst_diversity = min(len(dept_institutions) / 5.0, 1.0)  # normalize to max 5

            # Position score: lower week = more foundational = higher score
            avg_week = sum(weeks) / len(weeks) if weeks else 7
            position = max(0, 1 - (avg_week - 1) / 14)  # week 1 → 1.0, week 14 → 0.07

            # Citation weight: log-normalized
            citations = paper_citations.get(paper_id, 0) if paper_id else 0
            citation_w = math.log(citations + 1) / math.log(max_citations + 1) if max_citations > 0 else 0

            # Teaching score: placeholder (from Open Syllabus data if available)
            teaching = 0.0  # Will be populated when Open Syllabus data is available

            # User adjustment: capped
            user_adj = 0.0  # Applied when feedback exists

            # Combined score
            combined = (
                W_FREQUENCY * frequency
                + W_INSTITUTION * inst_diversity
                + W_CITATION * citation_w
                + W_TEACHING * teaching
                + W_POSITION * position
                + W_USER * user_adj
            )

            # Classify tier
            if frequency >= 0.6 and len(dept_institutions) >= 3:
                tier = ReadingTier.CANONICAL
                combined = max(combined, CANONICAL_SCORE_FLOOR)
            elif frequency >= 0.3:
                tier = ReadingTier.IMPORTANT
            elif frequency >= 0.1:
                tier = ReadingTier.SPECIALIZED
            else:
                tier = ReadingTier.NICHE

            # Get original title (not normalized)
            original_title = readings[0].get("external_title", title)

            scored_readings.append({
                "paper_id": paper_id,
                "reading_title": original_title[:500],
                "department": dept,
                "frequency_score": round(frequency, 4),
                "institution_diversity": round(inst_diversity, 4),
                "position_score": round(position, 4),
                "citation_weight": round(citation_w, 4),
                "teaching_score": round(teaching, 4),
                "user_adjustment": round(user_adj, 4),
                "combined_score": round(combined, 4),
                "tier": tier.value,
                "source_count": len(dept_readings),
                "source_institutions": list(dept_institutions),
                "authors": authors[:500] if authors else "",
                "publication_year": pub_year,
                "computed_at": datetime.now(timezone.utc).isoformat(),
            })

    # 8. Upsert into reading_scores table
    if scored_readings:
        # Clear old scores and insert new
        client.table("reading_scores").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
        # Batch insert in chunks of 50
        for i in range(0, len(scored_readings), 50):
            batch = scored_readings[i:i+50]
            client.table("reading_scores").insert(batch).execute()

    logger.info(
        f"Scored {len(scored_readings)} readings across "
        f"{len(dept_syllabi_count)} departments"
    )

    # Log tier distribution
    tier_counts = defaultdict(int)
    for r in scored_readings:
        tier_counts[r["tier"]] += 1
    for tier, count in sorted(tier_counts.items()):
        logger.info(f"  {tier}: {count}")

    return len(scored_readings)


def _normalize_title(title: str) -> str:
    """Normalize a reading title for grouping/dedup."""
    import re
    title = title.lower().strip()
    title = re.sub(r"[^a-z0-9\s]", "", title)
    title = re.sub(r"\s+", " ", title)
    # Remove common prefixes
    for prefix in ["course overview ", "course description "]:
        if title.startswith(prefix):
            title = title[len(prefix):]
    return title.strip()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    score_all_readings()
