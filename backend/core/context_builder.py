"""Context builder — extracts graph context for Navigator responses."""

import json
import logging
import re

from backend.integrations import supabase_client as db

logger = logging.getLogger(__name__)

# Hebrew and English stop words
STOP_WORDS = {
    # English
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "dare", "ought",
    "used", "to", "of", "in", "for", "on", "with", "at", "by", "from",
    "as", "into", "through", "during", "before", "after", "above", "below",
    "between", "out", "off", "over", "under", "again", "further", "then",
    "once", "here", "there", "when", "where", "why", "how", "all", "both",
    "each", "few", "more", "most", "other", "some", "such", "no", "nor",
    "not", "only", "own", "same", "so", "than", "too", "very", "just",
    "about", "up", "its", "it", "this", "that", "these", "those", "i",
    "me", "my", "we", "our", "you", "your", "he", "him", "his", "she",
    "her", "they", "them", "their", "what", "which", "who", "whom",
    "and", "but", "or", "if", "while", "because", "until", "although",
    "tell", "explain", "describe", "what's", "whats", "know", "think",
    # Hebrew
    "של", "את", "על", "עם", "מה", "איך", "למה", "מי", "זה", "זו", "אלה",
    "הוא", "היא", "הם", "הן", "אני", "אנחנו", "אתה", "את", "אתם",
    "לי", "לך", "לו", "לה", "לנו", "להם", "בין", "כל", "גם", "רק",
    "אבל", "או", "כי", "אם", "לא", "כן", "יותר", "פחות", "מאוד",
    "ספר", "תגיד", "תסביר",
}

# Max tokens for context string (~4000 tokens ≈ ~16000 chars)
MAX_CONTEXT_CHARS = 14000


def extract_keywords(message: str) -> list[str]:
    """Extract meaningful keywords from user message."""
    # Remove punctuation, split on whitespace
    words = re.findall(r'[\w\u0590-\u05FF]+', message.lower())
    keywords = [w for w in words if w not in STOP_WORDS and len(w) > 2]
    # Also try multi-word phrases (bigrams)
    if len(words) >= 2:
        for i in range(len(words) - 1):
            bigram = f"{words[i]} {words[i+1]}"
            if words[i] not in STOP_WORDS or words[i+1] not in STOP_WORDS:
                keywords.append(bigram)
    return keywords[:15]  # Cap at 15 keywords


async def build_context(user_message: str) -> tuple[str, list[dict]]:
    """Build graph context for a user message.

    Returns (context_text, concepts_referenced).
    """
    keywords = extract_keywords(user_message)
    if not keywords:
        return ("No specific concepts found in the knowledge graph for this query.", [])

    # Search concepts for each keyword, collect unique matches
    seen_ids = set()
    matched_concepts = []
    for kw in keywords:
        results = await db.search_concepts(kw, limit=5)
        for c in results:
            if c["id"] not in seen_ids:
                seen_ids.add(c["id"])
                matched_concepts.append(c)
            if len(matched_concepts) >= 10:
                break
        if len(matched_concepts) >= 10:
            break

    if not matched_concepts:
        return ("No matching concepts found in the knowledge graph.", [])

    # Take top 5 for deep context
    top_concepts = matched_concepts[:5]
    concepts_referenced = [
        {"id": str(c["id"]), "name": c["name"]}
        for c in matched_concepts[:10]
    ]

    parts = []
    parts.append(f"Found {len(matched_concepts)} relevant concepts in the knowledge graph.\n")

    # For each top concept, gather papers, claims, neighborhood
    for concept in top_concepts:
        cid = str(concept["id"])
        section = f"## {concept['name']} ({concept.get('type', 'concept')})"
        if concept.get("definition"):
            section += f"\nDefinition: {concept['definition']}"

        confidence = concept.get("confidence", 0.5)
        if confidence > 0.85:
            section += f"\nConfidence: HIGH (well-established)"
        elif confidence >= 0.6:
            section += f"\nConfidence: MODERATE (likely accurate)"
        else:
            section += f"\nConfidence: LOW (needs more evidence)"

        # Papers
        papers = await db.get_papers_for_concept(cid, limit=3)
        if papers:
            section += "\nKey papers:"
            for p in papers:
                authors_raw = p.get("authors", [])
                if isinstance(authors_raw, str):
                    try:
                        authors_raw = json.loads(authors_raw)
                    except (json.JSONDecodeError, TypeError):
                        authors_raw = []
                if authors_raw and isinstance(authors_raw[0], dict):
                    first_author = authors_raw[0].get("name", "Unknown")
                elif authors_raw and isinstance(authors_raw[0], str):
                    first_author = authors_raw[0]
                else:
                    first_author = "Unknown"
                section += f"\n  - {first_author} ({p.get('publication_year', '?')}): \"{p.get('title', 'Untitled')}\" [cited: {p.get('cited_by_count', 0)}]"

            # Claims from these papers
            paper_ids = [str(p["id"]) for p in papers]
            claims = await db.get_claims_for_papers(paper_ids, limit=3)
            if claims:
                section += "\nKey claims:"
                for cl in claims:
                    strength = cl.get("strength", "moderate")
                    section += f"\n  - [{strength}] {cl.get('claim_text', '')}"

        # Neighborhood
        try:
            neighbors = await db.get_concept_neighborhood(cid, depth=1)
            if neighbors:
                section += "\nConnected concepts:"
                for n in neighbors[:5]:
                    section += f"\n  - {n.get('concept_name', '?')} ({n.get('relationship_type', 'related')}, conf: {n.get('relationship_confidence', 0):.1f})"
        except Exception:
            pass  # RPC might not be set up yet

        parts.append(section)

        # Check total length
        if len("\n\n".join(parts)) > MAX_CONTEXT_CHARS:
            break

    # Search controversies
    for kw in keywords[:3]:
        try:
            contros = await db.search_controversies(kw, limit=2)
            if contros:
                parts.append("## Active Debates")
                for c in contros:
                    parts.append(f"- {c.get('title', 'Untitled debate')}: {c.get('description', '')[:200]}")
                break
        except Exception:
            pass

    context_text = "\n\n".join(parts)
    # Truncate if still too long
    if len(context_text) > MAX_CONTEXT_CHARS:
        context_text = context_text[:MAX_CONTEXT_CHARS] + "\n[... context truncated]"

    return (context_text, concepts_referenced)


async def get_library_context(user_id: str) -> str:
    """Build context from user's saved papers and interest profile.

    Distinguishes task-driven searches from genuine sustained interests.
    """
    try:
        from backend.core.reading_recommender import build_interest_profile

        client = db.get_client()

        # Get saved paper counts by context
        saved = (
            client.table("user_papers")
            .select("save_context, status")
            .eq("user_id", user_id)
            .execute()
        )
        if not saved.data:
            return ""

        total = len(saved.data)
        by_context = {}
        by_status = {}
        for row in saved.data:
            ctx = row.get("save_context", "browsing")
            by_context[ctx] = by_context.get(ctx, 0) + 1
            st = row.get("status", "unread")
            by_status[st] = by_status.get(st, 0) + 1

        # Build interest profile
        profile = await build_interest_profile(user_id)

        parts = [f"User's library: {total} saved papers"]
        if by_status.get("completed"):
            parts.append(f"  Completed: {by_status['completed']}")
        if by_status.get("reading"):
            parts.append(f"  Currently reading: {by_status['reading']}")

        if profile:
            # Separate genuine interests from task-driven
            genuine = {k: v for k, v in profile.items() if v >= 0.6}
            task_driven = {k: v for k, v in profile.items() if v < 0.4}

            if genuine:
                parts.append(f"  Sustained interests: {', '.join(genuine.keys())}")
            if task_driven:
                parts.append(f"  Task-driven searches: {', '.join(task_driven.keys())}")

        return "\n".join(parts)
    except Exception as e:
        logger.warning(f"Library context error: {e}")
        return ""


async def get_highlight_context(user_id: str) -> str:
    """Build context from user's recent highlights, grouped by concept."""
    try:
        client = db.get_client()
        highlights = (
            client.table("highlights")
            .select("highlighted_text, annotation, concept_ids, source_type, created_at")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(20)
            .execute()
        )
        if not highlights.data:
            return ""

        parts = [f"User's recent highlights ({len(highlights.data)}):"]
        for h in highlights.data[:10]:
            text = h.get("highlighted_text", "")[:100]
            annotation = h.get("annotation", "")
            line = f"  - \"{text}\""
            if annotation:
                line += f" (note: {annotation[:60]})"
            parts.append(line)

        return "\n".join(parts)
    except Exception as e:
        logger.warning(f"Highlight context error: {e}")
        return ""


async def get_reading_behavior_context(user_id: str) -> str:
    """Build context from reading sessions — concepts the user lingered on."""
    try:
        client = db.get_client()
        sessions = (
            client.table("reading_sessions")
            .select("total_seconds, concept_focus")
            .eq("user_id", user_id)
            .order("started_at", desc=True)
            .limit(20)
            .execute()
        )
        if not sessions.data:
            return ""

        # Aggregate concept focus times
        concept_times: dict[str, int] = {}
        total_time = 0
        for s in sessions.data:
            total_time += s.get("total_seconds", 0)
            focus = s.get("concept_focus") or {}
            for cid, secs in focus.items():
                if isinstance(secs, (int, float)):
                    concept_times[cid] = concept_times.get(cid, 0) + int(secs)

        if not concept_times:
            return f"User has {len(sessions.data)} reading sessions ({total_time}s total)"

        # Get concept names
        top_ids = sorted(concept_times, key=concept_times.get, reverse=True)[:5]
        concepts = (
            client.table("concepts")
            .select("id, name")
            .in_("id", top_ids)
            .execute()
        )
        name_map = {c["id"]: c["name"] for c in (concepts.data or [])}

        parts = [f"Reading behavior ({len(sessions.data)} sessions, {total_time}s total):"]
        for cid in top_ids:
            name = name_map.get(cid, cid)
            secs = concept_times[cid]
            parts.append(f"  - Spent {secs}s reading about {name}")

        return "\n".join(parts)
    except Exception as e:
        logger.warning(f"Reading behavior context error: {e}")
        return ""


async def get_syllabus_context(user_id: str) -> str:
    """Build context from user's active syllabus — where they are in the curriculum."""
    try:
        client = db.get_client()

        # Get active user syllabi
        user_syllabi = (
            client.table("user_syllabi")
            .select("custom_title, progress, syllabus_id, syllabi(title, department)")
            .eq("user_id", user_id)
            .eq("is_active", True)
            .limit(3)
            .execute()
        )
        if not user_syllabi.data:
            return ""

        parts = ["Active curricula:"]
        for us in user_syllabi.data:
            syl = us.get("syllabi") or {}
            title = us.get("custom_title") or syl.get("title", "Untitled")
            dept = syl.get("department", "")
            progress = us.get("progress") or {}
            completed = sum(1 for v in progress.values() if isinstance(v, dict) and v.get("status") == "completed")

            # Get total readings for this syllabus
            readings = (
                client.table("syllabus_readings")
                .select("id", count="exact")
                .eq("syllabus_id", us["syllabus_id"])
                .execute()
            )
            total = readings.count or 0
            pct = round(completed / total * 100) if total > 0 else 0

            parts.append(f"  - {title} ({dept}): {completed}/{total} readings ({pct}% complete)")

        return "\n".join(parts)
    except Exception as e:
        logger.warning(f"Syllabus context error: {e}")
        return ""
