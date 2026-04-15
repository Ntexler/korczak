"""Active Learning Engine — contradiction detection, depth slider, and quiz generation.

Provides the AI-powered features that make Korczak's learning experience unique:
1. Inline evidence map — support/contradict counts per claim
2. Depth-adaptive explanations — high school to PhD level
3. Active recall quiz — generate questions from the knowledge graph
"""

import logging
import json
import random

from backend.config import settings
from backend.integrations.supabase_client import get_client

logger = logging.getLogger(__name__)

# ─── 1. Claim Evidence Map ─────────────────────────────────────────────────────

async def get_claim_evidence_map(concept_id: str) -> list[dict]:
    """Get claims for a concept with inline support/contradiction indicators.

    For each claim, returns:
    - The claim itself
    - How many papers support it
    - How many papers contradict it
    - Whether it's actively debated
    - Contradicting claim texts (if any)
    """
    client = get_client()

    # Get papers for this concept
    from backend.integrations.supabase_client import get_papers_for_concept
    papers = await get_papers_for_concept(concept_id, limit=20)
    if not papers:
        return []

    paper_ids = [str(p["id"]) for p in papers]

    # Get all claims from these papers
    claims = client.table("claims").select(
        "id, paper_id, claim_text, evidence_type, strength, confidence"
    ).in_("paper_id", paper_ids).order("confidence", desc=True).execute()

    if not claims.data:
        return []

    # Get relationships involving these claims
    claim_ids = [c["id"] for c in claims.data]

    # Find CONTRADICTS / SUPPORTS relationships between claims or from concepts
    rels = client.table("relationships").select(
        "source_id, target_id, relationship_type, explanation, confidence"
    ).execute()

    # Build evidence map
    claim_support: dict[str, int] = {}
    claim_contradict: dict[str, int] = {}
    claim_contradictions: dict[str, list[str]] = {}

    claim_text_by_id = {c["id"]: c["claim_text"] for c in claims.data}

    for r in (rels.data or []):
        rel_type = r.get("relationship_type", "")
        src, tgt = r.get("source_id"), r.get("target_id")

        if rel_type in ("SUPPORTS", "BUILDS_ON"):
            if src in claim_text_by_id:
                claim_support[src] = claim_support.get(src, 0) + 1
            if tgt in claim_text_by_id:
                claim_support[tgt] = claim_support.get(tgt, 0) + 1

        elif rel_type in ("CONTRADICTS", "WEAKENS"):
            if src in claim_text_by_id:
                claim_contradict[src] = claim_contradict.get(src, 0) + 1
                if tgt in claim_text_by_id:
                    claim_contradictions.setdefault(src, []).append(claim_text_by_id[tgt])
            if tgt in claim_text_by_id:
                claim_contradict[tgt] = claim_contradict.get(tgt, 0) + 1
                if src in claim_text_by_id:
                    claim_contradictions.setdefault(tgt, []).append(claim_text_by_id[src])

    # Also count how many papers reference each claim's paper as support
    paper_citation_counts = {p["id"]: p.get("cited_by_count", 0) for p in papers}

    result = []
    for claim in claims.data[:10]:  # Cap at 10 claims
        cid = claim["id"]
        support_count = claim_support.get(cid, 0)
        contradict_count = claim_contradict.get(cid, 0)
        contradictions = claim_contradictions.get(cid, [])

        # Determine status
        if contradict_count > 0 and support_count > 0:
            status = "debated"
        elif contradict_count > 0:
            status = "challenged"
        elif support_count >= 2:
            status = "well_supported"
        elif claim.get("strength") == "strong":
            status = "supported"
        else:
            status = "single_source"

        # Paper citation count as a proxy for support weight
        paper_citations = paper_citation_counts.get(claim["paper_id"], 0)

        result.append({
            "id": cid,
            "claim_text": claim["claim_text"],
            "evidence_type": claim.get("evidence_type"),
            "strength": claim.get("strength"),
            "confidence": claim.get("confidence", 0),
            "support_count": support_count,
            "contradict_count": contradict_count,
            "status": status,
            "paper_citations": paper_citations,
            "contradictions": contradictions[:3],  # max 3 contradicting claims
        })

    return result


# ─── 2. Depth-Adaptive Explanations ────────────────────────────────────────────

DEPTH_LEVELS = {
    1: {"label": "High School", "label_he": "תיכון", "prompt": "Explain like I'm a high school student. Use simple words, analogies to everyday life, no jargon at all. 2-3 sentences."},
    2: {"label": "Undergrad", "label_he": "תואר ראשון", "prompt": "Explain for a first-year university student. You can use basic academic terms but explain them. Give one concrete example. 3-4 sentences."},
    3: {"label": "Advanced", "label_he": "מתקדם", "prompt": "Explain for an advanced student who knows the basics of the field. Use proper terminology, mention key thinkers, reference methodological debates. 4-5 sentences."},
    4: {"label": "Graduate", "label_he": "תואר שני", "prompt": "Explain for a graduate student. Include nuances, ongoing debates, methodological critiques, and connections to adjacent fields. Be precise with terminology. 5-6 sentences."},
    5: {"label": "Expert", "label_he": "מומחה", "prompt": "Explain for a fellow researcher/expert. Assume deep background knowledge. Focus on cutting-edge debates, unresolved questions, methodological tensions, and recent developments. Be intellectually dense. 4-6 sentences."},
}


async def explain_at_depth(
    concept_id: str,
    depth: int,
    locale: str = "en",
    user_context: str | None = None,
) -> dict:
    """Generate an explanation at a specific depth level (1-5).

    1 = high school, 5 = expert.
    Optionally incorporates user context (what they already know).
    """
    depth = max(1, min(5, depth))
    level = DEPTH_LEVELS[depth]

    client = get_client()
    concept = client.table("concepts").select(
        "id, name, type, definition, paper_count"
    ).eq("id", concept_id).execute()

    if not concept.data:
        return None

    c = concept.data[0]

    # Get top papers for context
    from backend.integrations.supabase_client import get_papers_for_concept
    papers = await get_papers_for_concept(concept_id, limit=3)
    paper_context = ""
    if papers:
        paper_context = "\n\nKey works:\n" + "\n".join(
            f"- {p.get('title', '')} ({p.get('publication_year', '')}) — {p.get('cited_by_count', 0)} citations"
            for p in papers[:3]
        )

    # Get neighbor concepts for richer context
    neighbor_context = ""
    try:
        from backend.core.concept_enricher import get_enriched_neighbors
        neighbors = await get_enriched_neighbors(concept_id, depth=1)
        if neighbors:
            neighbor_context = "\n\nRelated concepts:\n" + "\n".join(
                f"- {n['concept']['name']} ({n['relationship_type']}): {n.get('explanation', '')}"
                for n in neighbors[:5]
            )
    except Exception:
        pass

    # Build pedagogical context
    pedagogy_block = ""
    try:
        from backend.core.pedagogy import get_teaching_strategy
        strategy = get_teaching_strategy(c.get("type", "concept"))
        pedagogy_block = (
            f"\n\nTEACHING APPROACH for {c.get('type', 'concept')}s: {strategy['description']}\n"
            f"Steps: {'; '.join(strategy['steps'][:3])}\n"
            f"Avoid: {'; '.join(strategy['common_mistakes'][:2])}\n"
            f"{strategy.get('analogy_prompt', '')}"
        )
    except Exception:
        pass

    # Build prompt
    lang = "Hebrew" if locale == "he" else "English"
    user_note = ""
    if user_context:
        user_note = f"\n\nThe student has noted: \"{user_context}\". Tailor your explanation to connect with what they already know."

    prompt = (
        f"{level['prompt']}\n\n"
        f"Concept: \"{c['name']}\" (type: {c.get('type', 'concept')})\n"
        f"Definition: {c.get('definition', 'N/A')[:300]}\n"
        f"{paper_context}{neighbor_context}{pedagogy_block}{user_note}\n\n"
        f"Respond in {lang}. Be warm and engaging."
    )

    try:
        from backend.integrations.claude_client import _call_claude

        # Use haiku for levels 1-3 (faster), sonnet for 4-5 (needs depth)
        model = settings.haiku_model if depth <= 3 else settings.sonnet_model
        max_tokens = 200 + depth * 100  # longer for deeper explanations

        response = await _call_claude(
            prompt,
            model=model,
            max_tokens=max_tokens,
            temperature=0.4,
        )

        return {
            "concept_id": c["id"],
            "concept_name": c["name"],
            "depth": depth,
            "depth_label": level["label"],
            "depth_label_he": level["label_he"],
            "explanation": response.text,
            "tokens_used": response.total_tokens,
        }
    except Exception as e:
        logger.warning(f"Depth explanation failed: {e}")
        return {
            "concept_id": c["id"],
            "concept_name": c["name"],
            "depth": depth,
            "depth_label": level["label"],
            "depth_label_he": level["label_he"],
            "explanation": c.get("definition") or f"{c['name']} is an academic concept.",
            "tokens_used": 0,
        }


# ─── 3. Active Recall Quiz ────────────────────────────────────────────────────

QUESTION_TYPES = [
    "definition",       # What is X?
    "distinction",      # What's the difference between X and Y?
    "evidence",         # What evidence supports X?
    "application",      # How is X applied in practice?
    "connection",       # How does X relate to Y?
    "critique",         # What are the main criticisms of X?
]


async def generate_quiz(
    concept_ids: list[str] | None = None,
    field_name: str | None = None,
    question_count: int = 5,
    locale: str = "en",
) -> list[dict]:
    """Generate quiz questions from the knowledge graph.

    Can target specific concepts or generate from a field.
    Mixes question types for varied practice.
    """
    client = get_client()

    # Get concepts to quiz on
    if concept_ids:
        concepts = client.table("concepts").select(
            "id, name, type, definition, paper_count"
        ).in_("id", concept_ids).execute()
        concept_list = concepts.data or []
    elif field_name:
        from backend.api.features import _normalize_field
        all_papers = client.table("papers").select(
            "id, subfield"
        ).not_.is_("subfield", "null").execute()
        field_paper_ids = [
            p["id"] for p in (all_papers.data or [])
            if _normalize_field(p.get("subfield", "")) == field_name
        ]
        if not field_paper_ids:
            return []

        cids = set()
        for i in range(0, len(field_paper_ids), 50):
            batch = field_paper_ids[i:i + 50]
            pc = client.table("paper_concepts").select("concept_id").in_("paper_id", batch).execute()
            for row in (pc.data or []):
                cids.add(row["concept_id"])

        concepts = client.table("concepts").select(
            "id, name, type, definition, paper_count"
        ).in_("id", list(cids)).order("paper_count", desc=True).limit(30).execute()
        concept_list = concepts.data or []
    else:
        return []

    if not concept_list:
        return []

    # Get relationships for distinction/connection questions
    concept_ids_set = {c["id"] for c in concept_list}
    rels = client.table("relationships").select(
        "source_id, target_id, relationship_type, explanation"
    ).execute()
    relevant_rels = [
        r for r in (rels.data or [])
        if r["source_id"] in concept_ids_set and r["target_id"] in concept_ids_set
    ]
    concept_name_map = {c["id"]: c["name"] for c in concept_list}

    # Get claims
    paper_ids = set()
    for c in concept_list[:20]:
        pc = client.table("paper_concepts").select("paper_id").eq(
            "concept_id", c["id"]
        ).limit(3).execute()
        for row in (pc.data or []):
            paper_ids.add(row["paper_id"])

    claims = []
    if paper_ids:
        claims_result = client.table("claims").select(
            "claim_text, evidence_type, strength, paper_id"
        ).in_("paper_id", list(paper_ids)).order("confidence", desc=True).limit(20).execute()
        claims = claims_result.data or []

    # Generate questions
    questions = []
    used_concepts = set()

    for _ in range(question_count * 3):  # generate more, pick best
        if len(questions) >= question_count:
            break

        q_type = random.choice(QUESTION_TYPES)
        q = _generate_question(
            q_type, concept_list, relevant_rels, claims,
            concept_name_map, used_concepts, locale,
        )
        if q:
            questions.append(q)
            if q.get("concept_id"):
                used_concepts.add(q["concept_id"])

    return questions[:question_count]


def _generate_question(
    q_type: str,
    concepts: list[dict],
    relationships: list[dict],
    claims: list[dict],
    name_map: dict[str, str],
    used: set[str],
    locale: str,
) -> dict | None:
    """Generate a single quiz question of the given type."""
    he = locale == "he"

    # Pick a concept not yet used
    available = [c for c in concepts if c["id"] not in used and c.get("definition")]
    if not available:
        available = [c for c in concepts if c.get("definition")]
    if not available:
        return None

    c = random.choice(available)

    if q_type == "definition":
        return {
            "type": "definition",
            "concept_id": c["id"],
            "question": f"{'מה הם ' if he else 'What is '}{c['name']}{'?' if not he else '?'}",
            "hint": c.get("type", "concept"),
            "answer": c.get("definition", ""),
            "difficulty": 1,
        }

    elif q_type == "distinction":
        # Find a pair with a relationship
        pairs = [
            r for r in relationships
            if r["source_id"] == c["id"] or r["target_id"] == c["id"]
        ]
        if not pairs:
            return None
        rel = random.choice(pairs)
        other_id = rel["target_id"] if rel["source_id"] == c["id"] else rel["source_id"]
        other_name = name_map.get(other_id, "?")

        return {
            "type": "distinction",
            "concept_id": c["id"],
            "question": (
                f"{'מה ההבדל בין ' if he else 'What is the difference between '}"
                f"{c['name']} {'לבין' if he else 'and'} {other_name}?"
            ),
            "hint": rel.get("relationship_type", "").replace("_", " ").lower(),
            "answer": rel.get("explanation", f"{c['name']} {rel.get('relationship_type', 'relates to')} {other_name}"),
            "difficulty": 3,
        }

    elif q_type == "evidence":
        # Find claims related to this concept
        concept_claims = [cl for cl in claims if cl.get("claim_text")]
        if not concept_claims:
            return None
        claim = random.choice(concept_claims)
        return {
            "type": "evidence",
            "concept_id": c["id"],
            "question": (
                f"{'איזה סוג ראיות תומך בטענה: ' if he else 'What type of evidence supports the claim: '}"
                f"\"{claim['claim_text'][:100]}{'...' if len(claim.get('claim_text', '')) > 100 else ''}\"?"
            ),
            "hint": c["name"],
            "answer": f"{claim.get('evidence_type', 'N/A')} ({claim.get('strength', 'N/A')})",
            "difficulty": 2,
        }

    elif q_type == "connection":
        pairs = [
            r for r in relationships
            if r["source_id"] == c["id"] or r["target_id"] == c["id"]
        ]
        if not pairs:
            return None
        rel = random.choice(pairs)
        other_id = rel["target_id"] if rel["source_id"] == c["id"] else rel["source_id"]
        other_name = name_map.get(other_id, "?")

        return {
            "type": "connection",
            "concept_id": c["id"],
            "question": (
                f"{'איך ' if he else 'How does '}{c['name']} "
                f"{'קשור ל-' if he else 'relate to '}{other_name}?"
            ),
            "hint": rel.get("relationship_type", "").replace("_", " ").lower(),
            "answer": rel.get("explanation", ""),
            "difficulty": 3,
        }

    elif q_type == "application":
        return {
            "type": "application",
            "concept_id": c["id"],
            "question": (
                f"{'תן דוגמה ליישום של ' if he else 'Give an example of how '}"
                f"{c['name']} {'בפרקטיקה.' if he else 'is applied in practice.'}"
            ),
            "hint": c.get("type", ""),
            "answer": c.get("definition", ""),
            "difficulty": 4,
        }

    elif q_type == "critique":
        contradictions = [
            r for r in relationships
            if r.get("relationship_type") == "CONTRADICTS"
            and (r["source_id"] == c["id"] or r["target_id"] == c["id"])
        ]
        if contradictions:
            rel = contradictions[0]
            other_id = rel["target_id"] if rel["source_id"] == c["id"] else rel["source_id"]
            other_name = name_map.get(other_id, "?")
            return {
                "type": "critique",
                "concept_id": c["id"],
                "question": (
                    f"{'מהי הביקורת המרכזית על ' if he else 'What is the main critique of '}"
                    f"{c['name']}?"
                ),
                "hint": f"Think about {other_name}",
                "answer": rel.get("explanation", f"Challenged by {other_name}"),
                "difficulty": 4,
            }
        return None

    return None
