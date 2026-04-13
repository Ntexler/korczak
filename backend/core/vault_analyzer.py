"""Vault Analyzer — map user's Obsidian notes to Korczak's knowledge graph.

Core capabilities:
1. Note-to-concept mapping (fuzzy match + embedding similarity)
2. Gap detection (what's missing from user's knowledge)
3. Hidden connection discovery (links the user doesn't see)
4. Misconception detection (via Claude analysis)
5. Progress calculation (fog of war from real notes)
"""

import logging
from dataclasses import dataclass, field

from backend.core.vault_parser import ParsedNote, VaultStats, compute_vault_stats
from backend.integrations.supabase_client import get_client

logger = logging.getLogger(__name__)


@dataclass
class NoteMapping:
    """A mapping from a user note to a Korczak concept."""
    note_title: str
    concept_id: str | None
    concept_name: str | None
    confidence: float  # 0-1
    match_method: str  # "exact", "fuzzy", "embedding", "none"
    note_excerpt: str = ""
    note_tags: list[str] = field(default_factory=list)
    outgoing_links: list[str] = field(default_factory=list)


@dataclass
class GapInsight:
    """A gap in the user's knowledge."""
    concept_name: str
    concept_id: str
    concept_type: str
    paper_count: int
    why: str  # why this gap matters


@dataclass
class ConnectionInsight:
    """A hidden connection between user's notes."""
    note_a: str
    note_b: str
    connection_concept: str  # the concept that bridges them
    relationship_type: str
    explanation: str


@dataclass
class VaultAnalysisResult:
    """Complete analysis result from a vault."""
    mappings: list[NoteMapping]
    gaps: list[GapInsight]
    connections: list[ConnectionInsight]
    stats: VaultStats
    field_name: str | None
    coverage_pct: float  # % of field concepts covered
    strengths: list[str]  # areas where user is strong


def _normalize(name: str) -> str:
    """Normalize a name for fuzzy comparison."""
    return name.lower().strip().replace("-", " ").replace("_", " ")


async def _get_all_concepts(field_name: str | None = None, limit: int = 500) -> list[dict]:
    """Fetch concepts, optionally filtered to a field."""
    client = get_client()

    if field_name:
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

        concept_ids = set()
        for i in range(0, len(field_paper_ids), 50):
            batch = field_paper_ids[i:i + 50]
            pc = client.table("paper_concepts").select(
                "concept_id"
            ).in_("paper_id", batch).execute()
            for row in (pc.data or []):
                concept_ids.add(row["concept_id"])

        if not concept_ids:
            return []

        concepts = client.table("concepts").select(
            "id, name, type, definition, paper_count, confidence"
        ).in_("id", list(concept_ids)).order(
            "paper_count", desc=True
        ).limit(limit).execute()
        return concepts.data or []
    else:
        concepts = client.table("concepts").select(
            "id, name, type, definition, paper_count, confidence"
        ).order("paper_count", desc=True).limit(limit).execute()
        return concepts.data or []


async def _get_relationships_for_concepts(concept_ids: set[str]) -> list[dict]:
    """Get relationships between a set of concepts."""
    client = get_client()
    relationships = client.table("relationships").select(
        "source_id, target_id, relationship_type, confidence, explanation"
    ).execute()

    return [
        r for r in (relationships.data or [])
        if r["source_id"] in concept_ids and r["target_id"] in concept_ids
    ]


def _detect_field(notes: list[ParsedNote], concepts: list[dict]) -> str | None:
    """Try to detect the primary field from vault content.

    Checks frontmatter fields, tags, and folder structure.
    """
    from backend.api.features import CORE_FIELDS

    field_scores: dict[str, int] = {}

    for note in notes:
        # Check frontmatter
        fm_field = note.frontmatter.get("field", "")
        if fm_field:
            for core in CORE_FIELDS:
                if core.lower() in fm_field.lower():
                    field_scores[core] = field_scores.get(core, 0) + 5

        # Check tags
        for tag in note.tags:
            for core in CORE_FIELDS:
                if core.lower().replace(" ", "-") in tag or core.lower().replace(" ", "") in tag:
                    field_scores[core] = field_scores.get(core, 0) + 2

        # Check folder names
        if note.folder:
            for core in CORE_FIELDS:
                if core.lower() in note.folder.lower():
                    field_scores[core] = field_scores.get(core, 0) + 3

    if field_scores:
        return max(field_scores, key=field_scores.get)
    return None


def _match_notes_to_concepts(
    notes: list[ParsedNote],
    concepts: list[dict],
) -> list[NoteMapping]:
    """Map each note to the best-matching Korczak concept.

    Matching strategy (in order):
    1. Exact match: note title == concept name (case-insensitive)
    2. Fuzzy match: note title contains concept name or vice versa
    3. Tag/heading match: concept name appears in tags or headings
    4. No match: note doesn't map to any concept
    """
    # Build normalized concept lookup
    concept_by_norm: dict[str, dict] = {}
    for c in concepts:
        norm = _normalize(c["name"])
        concept_by_norm[norm] = c

    mappings = []
    for note in notes:
        norm_title = _normalize(note.title)
        best_match = None
        best_conf = 0.0
        method = "none"

        # 1. Exact match
        if norm_title in concept_by_norm:
            best_match = concept_by_norm[norm_title]
            best_conf = 0.95
            method = "exact"
        else:
            # 2. Fuzzy: title contains concept name or vice versa
            for norm_name, concept in concept_by_norm.items():
                if len(norm_name) < 4:
                    continue  # skip very short names to avoid false matches

                if norm_name in norm_title:
                    score = len(norm_name) / max(len(norm_title), 1)
                    if score > best_conf:
                        best_match = concept
                        best_conf = min(0.8, 0.5 + score * 0.3)
                        method = "fuzzy"
                elif norm_title in norm_name and len(norm_title) > 5:
                    score = len(norm_title) / max(len(norm_name), 1)
                    if score > best_conf:
                        best_match = concept
                        best_conf = min(0.7, 0.4 + score * 0.3)
                        method = "fuzzy"

            # 3. Tag/heading match
            if best_conf < 0.5:
                note_tokens = set(
                    note.tags
                    + [_normalize(h) for h in note.headings]
                    + [_normalize(l) for l in note.wikilinks]
                )
                for norm_name, concept in concept_by_norm.items():
                    if norm_name in note_tokens:
                        best_match = concept
                        best_conf = 0.6
                        method = "fuzzy"
                        break

        mappings.append(NoteMapping(
            note_title=note.title,
            concept_id=best_match["id"] if best_match else None,
            concept_name=best_match["name"] if best_match else None,
            confidence=best_conf,
            match_method=method,
            note_excerpt=note.excerpt,
            note_tags=note.tags,
            outgoing_links=note.wikilinks,
        ))

    return mappings


def _find_gaps(
    mappings: list[NoteMapping],
    concepts: list[dict],
) -> list[GapInsight]:
    """Find important concepts the user hasn't written about.

    Prioritizes:
    - High paper_count concepts (foundational)
    - Concepts connected to what the user already knows
    - Prerequisites of mapped concepts
    """
    mapped_ids = {m.concept_id for m in mappings if m.concept_id}
    all_concept_ids = {c["id"] for c in concepts}

    missing = []
    for c in concepts:
        if c["id"] in mapped_ids:
            continue

        pc = c.get("paper_count", 0)
        if pc < 2:
            continue  # skip obscure concepts

        # Determine importance
        if pc >= 10:
            why = f"Foundational concept ({pc} papers) — appears frequently in the literature"
        elif pc >= 5:
            why = f"Core concept ({pc} papers) — important for understanding the field"
        else:
            why = f"Notable concept ({pc} papers) — complements your existing knowledge"

        missing.append(GapInsight(
            concept_name=c["name"],
            concept_id=c["id"],
            concept_type=c.get("type", "concept"),
            paper_count=pc,
            why=why,
        ))

    # Sort by paper_count (most important first), cap at 15
    missing.sort(key=lambda g: -g.paper_count)
    return missing[:15]


async def _find_hidden_connections(
    mappings: list[NoteMapping],
    concepts: list[dict],
) -> list[ConnectionInsight]:
    """Find connections between user's notes that the user hasn't linked.

    Looks for pairs of mapped notes that are connected in Korczak's graph
    but NOT linked via [[wikilinks]] in the user's vault.
    """
    mapped = [m for m in mappings if m.concept_id]
    if len(mapped) < 2:
        return []

    mapped_ids = {m.concept_id for m in mapped}
    concept_name_by_id = {m.concept_id: m.concept_name for m in mapped}
    note_by_concept = {m.concept_id: m.note_title for m in mapped}

    # Build set of existing user links (note_title -> linked note titles)
    user_links: dict[str, set[str]] = {}
    for m in mapped:
        user_links[m.note_title] = set(m.outgoing_links)

    # Get graph relationships between mapped concepts
    relationships = await _get_relationships_for_concepts(mapped_ids)

    connections = []
    seen_pairs: set[tuple[str, str]] = set()

    for rel in relationships:
        src_id, tgt_id = rel["source_id"], rel["target_id"]
        if src_id not in note_by_concept or tgt_id not in note_by_concept:
            continue

        note_a = note_by_concept[src_id]
        note_b = note_by_concept[tgt_id]

        # Skip if user already linked these
        if note_b in user_links.get(note_a, set()) or note_a in user_links.get(note_b, set()):
            continue

        # Skip duplicate pairs
        pair = tuple(sorted([note_a, note_b]))
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)

        rel_type = rel.get("relationship_type", "RELATED")
        explanation = rel.get("explanation", "")
        bridge = concept_name_by_id.get(src_id, "")

        if not explanation:
            explanation = f"{concept_name_by_id.get(src_id, note_a)} {rel_type.lower().replace('_', ' ')} {concept_name_by_id.get(tgt_id, note_b)}"

        connections.append(ConnectionInsight(
            note_a=note_a,
            note_b=note_b,
            connection_concept=bridge,
            relationship_type=rel_type,
            explanation=explanation,
        ))

    # Sort by relationship confidence, cap at 10
    connections.sort(key=lambda c: c.relationship_type)
    return connections[:10]


def _identify_strengths(
    mappings: list[NoteMapping],
    concepts: list[dict],
) -> list[str]:
    """Identify areas where the user has strong coverage."""
    mapped_ids = {m.concept_id for m in mappings if m.concept_id}
    if not mapped_ids:
        return []

    # Group concepts by type
    type_total: dict[str, int] = {}
    type_mapped: dict[str, int] = {}

    for c in concepts:
        ctype = c.get("type", "concept")
        type_total[ctype] = type_total.get(ctype, 0) + 1
        if c["id"] in mapped_ids:
            type_mapped[ctype] = type_mapped.get(ctype, 0) + 1

    strengths = []
    for ctype, total in type_total.items():
        mapped_count = type_mapped.get(ctype, 0)
        if total >= 3 and mapped_count / total >= 0.4:
            pct = int(mapped_count / total * 100)
            strengths.append(
                f"Strong in {ctype}s — you cover {mapped_count}/{total} ({pct}%)"
            )

    return strengths


async def analyze_vault(
    notes: list[ParsedNote],
    user_id: str,
    field_name: str | None = None,
) -> VaultAnalysisResult:
    """Full vault analysis pipeline.

    1. Compute vault stats
    2. Detect field (if not provided)
    3. Fetch relevant concepts
    4. Map notes to concepts
    5. Find gaps
    6. Discover hidden connections
    7. Identify strengths
    """
    stats = compute_vault_stats(notes)

    # Detect field if not specified
    concepts = await _get_all_concepts(field_name=None, limit=500)
    if not field_name:
        field_name = _detect_field(notes, concepts)

    # Get field-specific concepts if field detected
    if field_name:
        field_concepts = await _get_all_concepts(field_name=field_name, limit=300)
        if field_concepts:
            concepts = field_concepts

    # Map notes to concepts
    mappings = _match_notes_to_concepts(notes, concepts)

    # Count coverage
    mapped_count = sum(1 for m in mappings if m.concept_id)
    coverage_pct = (mapped_count / len(concepts) * 100) if concepts else 0

    # Find gaps
    gaps = _find_gaps(mappings, concepts)

    # Find hidden connections
    connections = await _find_hidden_connections(mappings, concepts)

    # Identify strengths
    strengths = _identify_strengths(mappings, concepts)

    return VaultAnalysisResult(
        mappings=mappings,
        gaps=gaps,
        connections=connections,
        stats=stats,
        field_name=field_name,
        coverage_pct=round(coverage_pct, 1),
        strengths=strengths,
    )


async def save_analysis(
    result: VaultAnalysisResult,
    user_id: str,
) -> str:
    """Persist the analysis results to database. Returns the analysis ID."""
    client = get_client()

    # Save vault analysis record
    analysis = client.table("vault_analyses").insert({
        "user_id": user_id,
        "note_count": result.stats.note_count,
        "total_links": result.stats.total_links,
        "total_tags": result.stats.total_tags,
        "mapped_concepts": sum(1 for m in result.mappings if m.concept_id),
        "unmapped_notes": sum(1 for m in result.mappings if not m.concept_id),
        "coverage_pct": result.coverage_pct,
        "field": result.field_name,
        "raw_stats": {
            "total_words": result.stats.total_words,
            "avg_note_length": result.stats.avg_note_length,
            "unique_tags": result.stats.unique_tags,
            "folders": result.stats.folders,
            "top_tags": result.stats.top_tags[:10],
            "most_linked": result.stats.most_linked[:10],
        },
        "status": "complete",
    }).execute()

    if not analysis.data:
        raise RuntimeError("Failed to save vault analysis")
    analysis_id = analysis.data[0]["id"]

    # Save note mappings (batch insert)
    mapping_rows = []
    for m in result.mappings:
        mapping_rows.append({
            "vault_analysis_id": analysis_id,
            "user_id": user_id,
            "note_title": m.note_title,
            "note_tags": m.note_tags,
            "matched_concept_id": m.concept_id,
            "matched_concept_name": m.concept_name,
            "match_confidence": m.confidence,
            "note_excerpt": m.note_excerpt[:500] if m.note_excerpt else "",
            "outgoing_links": m.outgoing_links,
        })

    if mapping_rows:
        # Insert in batches of 50
        for i in range(0, len(mapping_rows), 50):
            batch = mapping_rows[i:i + 50]
            client.table("vault_note_mappings").insert(batch).execute()

    # Save insights
    insights = []

    for gap in result.gaps[:10]:
        insights.append({
            "vault_analysis_id": analysis_id,
            "user_id": user_id,
            "insight_type": "gap",
            "title": f"Missing: {gap.concept_name}",
            "description": gap.why,
            "severity": "important" if gap.paper_count >= 10 else "suggestion",
            "related_concepts": [gap.concept_name],
            "action_prompt": f"Explain {gap.concept_name} and how it connects to what I already know",
        })

    for conn in result.connections[:10]:
        insights.append({
            "vault_analysis_id": analysis_id,
            "user_id": user_id,
            "insight_type": "hidden_connection",
            "title": f"Connection: {conn.note_a} \u2194 {conn.note_b}",
            "description": conn.explanation,
            "severity": "suggestion",
            "related_concepts": [conn.connection_concept],
            "related_notes": [conn.note_a, conn.note_b],
            "action_prompt": f"Explain how {conn.note_a} and {conn.note_b} are connected through {conn.connection_concept}",
        })

    for strength in result.strengths:
        insights.append({
            "vault_analysis_id": analysis_id,
            "user_id": user_id,
            "insight_type": "strength",
            "title": strength,
            "description": f"Your vault shows strong coverage in this area.",
            "severity": "info",
        })

    if insights:
        for i in range(0, len(insights), 20):
            batch = insights[i:i + 20]
            client.table("vault_insights").insert(batch).execute()

    # Create attention signals for important gaps
    signals = []
    for gap in result.gaps[:5]:
        signals.append({
            "user_id": user_id,
            "signal_type": "gap_detected",
            "direction": "neutral",
            "target_type": "concept",
            "target_id": gap.concept_id,
            "target_name": gap.concept_name,
            "context": f"Vault analysis: user has no notes on this {gap.concept_type} ({gap.paper_count} papers)",
            "status": "pending",
        })

    for conn in result.connections[:5]:
        signals.append({
            "user_id": user_id,
            "signal_type": "connection_found",
            "direction": "interest",
            "target_type": "concept",
            "target_name": conn.connection_concept,
            "context": f"Hidden connection between user notes '{conn.note_a}' and '{conn.note_b}'",
            "status": "pending",
        })

    if signals:
        client.table("attention_signals").insert(signals).execute()

    # Update user_knowledge for mapped concepts
    for m in result.mappings:
        if m.concept_id and m.confidence >= 0.5:
            # User has a note on this concept -> mark as at least partially understood
            existing = client.table("user_knowledge").select("id, understanding_level").eq(
                "user_id", user_id
            ).eq("concept_id", m.concept_id).execute()

            level = min(0.6, 0.3 + m.confidence * 0.3)  # vault note = at least 0.3 understanding

            if existing.data:
                # Only upgrade, never downgrade
                current = existing.data[0].get("understanding_level", 0)
                if level > current:
                    client.table("user_knowledge").update({
                        "understanding_level": level,
                    }).eq("id", existing.data[0]["id"]).execute()
            else:
                client.table("user_knowledge").insert({
                    "user_id": user_id,
                    "concept_id": m.concept_id,
                    "understanding_level": level,
                    "interaction_count": 1,
                }).execute()

    return analysis_id
