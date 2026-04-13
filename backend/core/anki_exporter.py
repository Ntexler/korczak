"""Anki Exporter — generate Anki-compatible flashcard decks from Korczak knowledge graph.

Exports as tab-separated text (importable into Anki) with rich card types:
- Definition cards: concept → definition
- Distinction cards: concept A vs B → explanation
- Evidence cards: claim → evidence type + strength
- Connection cards: concept A relates to B → relationship explanation

Format: TSV with front\tback\ttags
"""

import logging

from backend.integrations.supabase_client import get_client

logger = logging.getLogger(__name__)


async def generate_anki_deck(
    concept_ids: list[str] | None = None,
    field_name: str | None = None,
    locale: str = "en",
) -> dict:
    """Generate an Anki-compatible deck from concepts.

    Returns {filename, content, card_count} where content is TSV text.
    """
    client = get_client()

    # Get concepts
    if concept_ids:
        concepts = client.table("concepts").select(
            "id, name, type, definition, paper_count, confidence"
        ).in_("id", concept_ids).order("paper_count", desc=True).execute()
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
            return {"filename": "empty.txt", "content": "", "card_count": 0}

        cids = set()
        for i in range(0, len(field_paper_ids), 50):
            batch = field_paper_ids[i:i + 50]
            pc = client.table("paper_concepts").select("concept_id").in_("paper_id", batch).execute()
            for row in (pc.data or []):
                cids.add(row["concept_id"])

        concepts = client.table("concepts").select(
            "id, name, type, definition, paper_count, confidence"
        ).in_("id", list(cids)).order("paper_count", desc=True).limit(60).execute()
        concept_list = concepts.data or []
    else:
        return {"filename": "empty.txt", "content": "", "card_count": 0}

    if not concept_list:
        return {"filename": "empty.txt", "content": "", "card_count": 0}

    concept_ids_set = {c["id"] for c in concept_list}
    concept_name_map = {c["id"]: c["name"] for c in concept_list}

    # Get relationships
    rels = client.table("relationships").select(
        "source_id, target_id, relationship_type, explanation, confidence"
    ).execute()
    relevant_rels = [
        r for r in (rels.data or [])
        if r["source_id"] in concept_ids_set and r["target_id"] in concept_ids_set
        and r.get("explanation")
    ]

    # Get claims
    paper_ids = set()
    for c in concept_list[:30]:
        pc = client.table("paper_concepts").select("paper_id").eq(
            "concept_id", c["id"]
        ).limit(3).execute()
        for row in (pc.data or []):
            paper_ids.add(row["paper_id"])

    claims = []
    if paper_ids:
        claims_result = client.table("claims").select(
            "claim_text, evidence_type, strength, confidence"
        ).in_("paper_id", list(paper_ids)).order("confidence", desc=True).limit(30).execute()
        claims = claims_result.data or []

    he = locale == "he"
    cards: list[str] = []
    tag_base = (field_name or "korczak").lower().replace(" ", "_")

    # Header comment (Anki ignores lines starting with #)
    cards.append(f"#separator:tab")
    cards.append(f"#html:false")
    cards.append(f"#tags column:3")

    # 1. Definition cards
    for c in concept_list:
        if not c.get("definition"):
            continue
        front = f"{'מה זה ' if he else 'What is '}{c['name']}?"
        back = c["definition"]
        tags = f"{tag_base} {c.get('type', 'concept')} definition"
        cards.append(f"{_escape(front)}\t{_escape(back)}\t{tags}")

    # 2. Distinction cards (from relationships)
    seen_pairs = set()
    for r in relevant_rels:
        if r["relationship_type"] not in ("CONTRADICTS", "EXTENDS", "BUILDS_ON"):
            continue
        src = concept_name_map.get(r["source_id"], "")
        tgt = concept_name_map.get(r["target_id"], "")
        pair = tuple(sorted([src, tgt]))
        if pair in seen_pairs or not src or not tgt:
            continue
        seen_pairs.add(pair)

        rel_label = r["relationship_type"].replace("_", " ").lower()
        front = f"{'מה הקשר בין ' if he else 'How does '}{src} {'לבין' if he else 'relate to'} {tgt}?"
        back = f"{rel_label}: {r['explanation']}"
        tags = f"{tag_base} connection {r['relationship_type'].lower()}"
        cards.append(f"{_escape(front)}\t{_escape(back)}\t{tags}")

    # 3. Evidence cards (from claims)
    for claim in claims[:15]:
        if not claim.get("claim_text"):
            continue
        text = claim["claim_text"]
        if len(text) > 120:
            text = text[:117] + "..."
        front = (
            f"{'מהם הראיות לטענה: ' if he else 'What evidence supports: '}"
            f"\"{text}\""
        )
        back = (
            f"{'סוג: ' if he else 'Type: '}{claim.get('evidence_type', 'N/A')}\n"
            f"{'חוזק: ' if he else 'Strength: '}{claim.get('strength', 'N/A')}\n"
            f"{'ביטחון: ' if he else 'Confidence: '}{claim.get('confidence', 0) * 100:.0f}%"
        )
        tags = f"{tag_base} evidence {claim.get('evidence_type', 'unknown')}"
        cards.append(f"{_escape(front)}\t{_escape(back)}\t{tags}")

    # 4. Type identification cards
    for c in concept_list[:20]:
        front = f"{'מאיזה סוג הוא ' if he else 'What type of concept is '}{c['name']}?"
        back = f"{c.get('type', 'concept')} ({c.get('paper_count', 0)} {'מאמרים' if he else 'papers'})"
        tags = f"{tag_base} type_id"
        cards.append(f"{_escape(front)}\t{_escape(back)}\t{tags}")

    content = "\n".join(cards)
    safe_name = (field_name or "korczak").replace(" ", "_").replace("&", "and")
    filename = f"Korczak_{safe_name}_anki.txt"

    # card_count excludes header lines
    card_count = len([c for c in cards if not c.startswith("#")])

    return {
        "filename": filename,
        "content": content,
        "card_count": card_count,
    }


def _escape(text: str) -> str:
    """Escape text for TSV format — replace tabs and newlines."""
    return text.replace("\t", " ").replace("\n", " | ").replace("\r", "")
