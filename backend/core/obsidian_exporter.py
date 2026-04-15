"""Obsidian Exporter — serialize Korczak knowledge graph data into Obsidian-compatible Markdown.

Generates Markdown files with YAML frontmatter and [[wikilinks]] for seamless
integration with Obsidian vaults.
"""

import io
import logging
import zipfile
from datetime import datetime, timezone

from backend.integrations.supabase_client import get_client, get_papers_for_concept

logger = logging.getLogger(__name__)

# Relationship type labels for readable Markdown
REL_LABELS = {
    "BUILDS_ON": "Builds on",
    "CONTRADICTS": "Contradicts",
    "EXTENDS": "Extends",
    "APPLIES": "Applies",
    "ANALOGOUS_TO": "Analogous to",
    "PART_OF": "Part of",
    "PREREQUISITE_FOR": "Prerequisite for",
    "RESPONDS_TO": "Responds to",
    "INTRODUCES": "Introduces",
    "CITES": "Cites",
    "SUPPORTS": "Supports",
    "WEAKENS": "Weakens",
}


def _safe_filename(name: str) -> str:
    """Sanitize a name for use as a filename (strip problematic characters)."""
    return name.replace("/", "-").replace("\\", "-").replace(":", " -").replace('"', "'")


def _format_authors(authors) -> str:
    """Format authors list into a readable string."""
    if not authors:
        return "Unknown"
    if isinstance(authors, str):
        import json
        try:
            authors = json.loads(authors)
        except (json.JSONDecodeError, TypeError):
            return authors

    names = []
    for a in authors[:5]:
        if isinstance(a, dict):
            names.append(a.get("name", "Unknown"))
        elif isinstance(a, str):
            names.append(a)
    result = ", ".join(names)
    if len(authors) > 5:
        result += f" (+{len(authors) - 5} more)"
    return result


def _paper_note_name(paper: dict) -> str:
    """Generate a consistent note name for a paper, used in [[wikilinks]]."""
    authors = paper.get("authors", [])
    first_author = ""
    if authors:
        if isinstance(authors, str):
            import json
            try:
                authors = json.loads(authors)
            except (json.JSONDecodeError, TypeError):
                first_author = authors.split(",")[0].strip()
        if isinstance(authors, list) and authors:
            a = authors[0]
            first_author = a.get("name", str(a)) if isinstance(a, dict) else str(a)

    # Last name only
    if first_author:
        parts = first_author.strip().split()
        first_author = parts[-1] if parts else first_author

    year = paper.get("publication_year", "")
    title = paper.get("title", "Untitled")
    # Truncate long titles
    if len(title) > 60:
        title = title[:57] + "..."

    name = f"{first_author} {year} — {title}" if first_author else title
    return _safe_filename(name)


def concept_to_markdown(concept: dict, neighbors: list[dict] | None = None) -> str:
    """Convert a concept + its neighbors into Obsidian Markdown with YAML frontmatter."""
    name = concept.get("name", "Untitled")
    ctype = concept.get("type", "concept")
    definition = concept.get("definition", "")
    confidence = concept.get("confidence", 0)
    paper_count = concept.get("paper_count", 0)
    trend = concept.get("trend", "stable")
    controversy = concept.get("controversy_score", 0)
    key_papers = concept.get("key_papers", [])
    key_claims = concept.get("key_claims", [])

    # --- YAML Frontmatter ---
    lines = [
        "---",
        f"korczak_id: \"{concept.get('id', '')}\"",
        f"type: \"{ctype}\"",
        f"confidence: {confidence}",
        f"paper_count: {paper_count}",
        f"trend: \"{trend}\"",
    ]
    if controversy:
        lines.append(f"controversy_score: {controversy}")

    lines.append("tags:")
    lines.append("  - korczak")
    lines.append(f"  - {ctype}")
    lines.append(f"exported: \"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}\"")
    lines.append("---")
    lines.append("")

    # --- Title ---
    lines.append(f"# {name}")
    lines.append("")

    # --- Definition ---
    if definition:
        lines.append(f"> {definition}")
        lines.append("")

    # --- Metadata ---
    lines.append(f"**Type**: {ctype} | **Confidence**: {confidence * 100:.0f}% | **Trend**: {trend} | **Papers**: {paper_count}")
    lines.append("")

    # --- Key Claims ---
    if key_claims:
        lines.append("## Key Claims")
        lines.append("")
        for claim in key_claims:
            strength = claim.get("strength", "unknown")
            evidence = claim.get("evidence_type", "unknown")
            conf = claim.get("confidence", 0)
            lines.append(f"- {claim.get('claim_text', '')}  ")
            lines.append(f"  *{evidence} | {strength} | {conf * 100:.0f}%*")
        lines.append("")

    # --- Key Papers ---
    if key_papers:
        lines.append("## Key Papers")
        lines.append("")
        for paper in key_papers:
            note_name = _paper_note_name(paper)
            authors_str = _format_authors(paper.get("authors"))
            year = paper.get("publication_year", "")
            cited = paper.get("cited_by_count", 0)
            lines.append(f"- [[{note_name}]] — {authors_str} ({year}), {cited} citations")
        lines.append("")

    # --- Connections ---
    if neighbors:
        lines.append("## Connections")
        lines.append("")
        # Group by relationship type
        by_type: dict[str, list] = {}
        for n in neighbors:
            rel_type = n.get("relationship_type", "related")
            by_type.setdefault(rel_type, []).append(n)

        for rel_type, rels in by_type.items():
            label = REL_LABELS.get(rel_type, rel_type.replace("_", " ").title())
            lines.append(f"### {label}")
            lines.append("")
            for rel in rels:
                c = rel.get("concept", {})
                c_name = c.get("name", "Unknown")
                conf = rel.get("confidence", 0)
                explanation = rel.get("explanation", "")
                line = f"- [[{_safe_filename(c_name)}]] ({conf * 100:.0f}%)"
                if explanation:
                    line += f" — *{explanation}*"
                lines.append(line)
            lines.append("")

    # --- Notes section ---
    lines.append("## Notes")
    lines.append("")
    lines.append("*Add your personal notes here...*")
    lines.append("")

    return "\n".join(lines)


def paper_to_markdown(paper: dict, related_concepts: list[str] | None = None) -> str:
    """Convert a paper into Obsidian Markdown with YAML frontmatter."""
    title = paper.get("title", "Untitled")
    authors = paper.get("authors", [])
    year = paper.get("publication_year", "")
    doi = paper.get("doi", "")
    abstract = paper.get("abstract", "")
    cited = paper.get("cited_by_count", 0)
    paper_type = paper.get("paper_type", "")
    subfield = paper.get("subfield", "")

    authors_str = _format_authors(authors)

    # --- YAML Frontmatter ---
    lines = [
        "---",
        f"korczak_id: \"{paper.get('id', '')}\"",
    ]
    if doi:
        lines.append(f"doi: \"{doi}\"")
    if year:
        lines.append(f"year: {year}")
    lines.append(f"cited_by: {cited}")
    if paper_type:
        lines.append(f"paper_type: \"{paper_type}\"")
    if subfield:
        lines.append(f"field: \"{subfield}\"")
    lines.append("tags:")
    lines.append("  - korczak")
    lines.append("  - paper")
    if subfield:
        lines.append(f"  - {subfield.lower().replace(' ', '-')}")
    lines.append(f"exported: \"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}\"")
    lines.append("---")
    lines.append("")

    # --- Title ---
    lines.append(f"# {title}")
    lines.append("")

    # --- Metadata ---
    lines.append(f"**Authors**: {authors_str}")
    if year:
        lines.append(f"**Year**: {year}")
    if doi:
        lines.append(f"**DOI**: `{doi}`")
    lines.append(f"**Cited by**: {cited}")
    if paper_type:
        lines.append(f"**Type**: {paper_type}")
    lines.append("")

    # --- Abstract ---
    if abstract:
        lines.append("## Abstract")
        lines.append("")
        lines.append(abstract)
        lines.append("")

    # --- Related Concepts ---
    if related_concepts:
        lines.append("## Related Concepts")
        lines.append("")
        for concept_name in related_concepts:
            lines.append(f"- [[{_safe_filename(concept_name)}]]")
        lines.append("")

    # --- Notes ---
    lines.append("## Notes")
    lines.append("")
    lines.append("*Add your personal notes here...*")
    lines.append("")

    return "\n".join(lines)


async def export_concept(concept_id: str) -> dict:
    """Export a single concept as Obsidian Markdown.

    Returns {filename, content} for download.
    """
    from backend.core.concept_enricher import get_concept_with_context, get_enriched_neighbors

    concept = await get_concept_with_context(concept_id)
    if not concept:
        return None

    neighbors = await get_enriched_neighbors(concept_id, depth=1)
    markdown = concept_to_markdown(concept, neighbors)
    filename = f"{_safe_filename(concept['name'])}.md"

    return {"filename": filename, "content": markdown}


async def export_field(field_name: str) -> bytes:
    """Export all concepts + papers in a field as a ZIP of Obsidian Markdown files.

    Structure:
      Korczak - {field}/
        Concepts/
          {concept_name}.md
        Papers/
          {author year — title}.md
        _Index.md
    """
    from backend.core.concept_enricher import get_concept_with_context, get_enriched_neighbors

    client = get_client()

    # Import field normalizer
    from backend.api.features import _normalize_field

    # Get papers in this field
    all_papers = client.table("papers").select(
        "id, title, authors, publication_year, doi, abstract, cited_by_count, paper_type, subfield"
    ).not_.is_("subfield", "null").execute()

    field_papers = [
        p for p in (all_papers.data or [])
        if _normalize_field(p.get("subfield", "")) == field_name
    ]
    field_paper_ids = {p["id"] for p in field_papers}

    # Get concept IDs for these papers
    concept_ids = set()
    paper_id_list = list(field_paper_ids)
    for i in range(0, len(paper_id_list), 50):
        batch = paper_id_list[i:i + 50]
        pc = client.table("paper_concepts").select(
            "concept_id, paper_id"
        ).in_("paper_id", batch).execute()
        for row in (pc.data or []):
            concept_ids.add(row["concept_id"])

    # Get concept data
    concepts_data = []
    if concept_ids:
        concepts = client.table("concepts").select(
            "id, name, type, definition, paper_count, confidence, trend, controversy_score"
        ).in_("id", list(concept_ids)).order("paper_count", desc=True).execute()
        concepts_data = concepts.data or []

    # Get relationships between these concepts
    concept_id_set = {c["id"] for c in concepts_data}
    relationships = client.table("relationships").select(
        "source_id, target_id, relationship_type, confidence, explanation"
    ).execute()

    # Build neighbor map: concept_id -> [neighbor_info]
    neighbor_map: dict[str, list[dict]] = {}
    concept_name_map = {c["id"]: c["name"] for c in concepts_data}

    for r in (relationships.data or []):
        src, tgt = r["source_id"], r["target_id"]
        if src in concept_id_set and tgt in concept_id_set:
            neighbor_map.setdefault(src, []).append({
                "concept": {"id": tgt, "name": concept_name_map.get(tgt, "Unknown")},
                "relationship_type": r["relationship_type"],
                "confidence": r.get("confidence", 0.5),
                "explanation": r.get("explanation"),
            })
            # Reverse direction too
            neighbor_map.setdefault(tgt, []).append({
                "concept": {"id": src, "name": concept_name_map.get(src, "Unknown")},
                "relationship_type": r["relationship_type"],
                "confidence": r.get("confidence", 0.5),
                "explanation": r.get("explanation"),
            })

    # Build paper → concept_names map
    paper_concepts_map: dict[str, list[str]] = {}
    for i in range(0, len(paper_id_list), 50):
        batch = paper_id_list[i:i + 50]
        pc = client.table("paper_concepts").select(
            "concept_id, paper_id"
        ).in_("paper_id", batch).execute()
        for row in (pc.data or []):
            cname = concept_name_map.get(row["concept_id"])
            if cname:
                paper_concepts_map.setdefault(row["paper_id"], []).append(cname)

    # Also get key papers + claims per concept for richer concept notes
    concept_papers_map: dict[str, list[dict]] = {}
    concept_claims_map: dict[str, list[dict]] = {}

    if paper_id_list:
        # Get paper_concepts with relevance for ranking
        for concept in concepts_data:
            cid = concept["id"]
            pc_result = client.table("paper_concepts").select(
                "paper_id, relevance"
            ).eq("concept_id", cid).order("relevance", desc=True).limit(5).execute()

            matching_papers = []
            for pc_row in (pc_result.data or []):
                pid = pc_row["paper_id"]
                for p in field_papers:
                    if p["id"] == pid:
                        matching_papers.append(p)
                        break
            concept_papers_map[cid] = matching_papers

        # Get claims
        claims_result = client.table("claims").select(
            "paper_id, claim_text, evidence_type, strength, confidence"
        ).in_("paper_id", paper_id_list).order("confidence", desc=True).execute()

        # Map claims to concepts via papers
        paper_to_concepts = {}
        for cid, papers in concept_papers_map.items():
            for p in papers:
                paper_to_concepts.setdefault(p["id"], []).append(cid)

        for claim in (claims_result.data or []):
            pid = claim["paper_id"]
            for cid in paper_to_concepts.get(pid, []):
                concept_claims_map.setdefault(cid, []).append(claim)

    # --- Build ZIP ---
    buf = io.BytesIO()
    folder = f"Korczak — {field_name}"

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Concept files
        for concept in concepts_data:
            cid = concept["id"]
            concept["key_papers"] = concept_papers_map.get(cid, [])
            concept["key_claims"] = (concept_claims_map.get(cid, []) or [])[:5]
            neighbors = neighbor_map.get(cid, [])
            md = concept_to_markdown(concept, neighbors)
            fname = _safe_filename(concept["name"])
            zf.writestr(f"{folder}/Concepts/{fname}.md", md)

        # Paper files
        for paper in field_papers:
            related = paper_concepts_map.get(paper["id"], [])
            md = paper_to_markdown(paper, related)
            fname = _paper_note_name(paper)
            zf.writestr(f"{folder}/Papers/{fname}.md", md)

        # Index file
        index = _build_index(field_name, concepts_data, field_papers)
        zf.writestr(f"{folder}/_Index.md", index)

    buf.seek(0)
    return buf.read()


def _build_index(field_name: str, concepts: list[dict], papers: list[dict]) -> str:
    """Build an index note for the vault folder."""
    lines = [
        "---",
        f"field: \"{field_name}\"",
        f"concepts: {len(concepts)}",
        f"papers: {len(papers)}",
        f"exported: \"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}\"",
        "tags:",
        "  - korczak",
        "  - index",
        "---",
        "",
        f"# {field_name} — Korczak Knowledge Export",
        "",
        f"Exported from [Korczak AI](https://korczak.ai) on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}.",
        "",
        f"**{len(concepts)} concepts** | **{len(papers)} papers**",
        "",
        "## Concepts",
        "",
    ]

    # Group concepts by type
    by_type: dict[str, list] = {}
    for c in concepts:
        by_type.setdefault(c.get("type", "concept"), []).append(c)

    for ctype, items in sorted(by_type.items()):
        lines.append(f"### {ctype.title()} ({len(items)})")
        lines.append("")
        for c in items[:20]:  # Cap at 20 per type in index
            lines.append(f"- [[{_safe_filename(c['name'])}]] — {c.get('paper_count', 0)} papers, {c.get('confidence', 0) * 100:.0f}% confidence")
        if len(items) > 20:
            lines.append(f"- *...and {len(items) - 20} more*")
        lines.append("")

    lines.append("## Papers")
    lines.append("")
    # Sort by citations
    sorted_papers = sorted(papers, key=lambda p: p.get("cited_by_count", 0), reverse=True)
    for p in sorted_papers[:30]:
        note = _paper_note_name(p)
        year = p.get("publication_year", "")
        cited = p.get("cited_by_count", 0)
        lines.append(f"- [[{note}]] ({year}) — {cited} citations")
    if len(papers) > 30:
        lines.append(f"- *...and {len(papers) - 30} more*")
    lines.append("")

    return "\n".join(lines)
