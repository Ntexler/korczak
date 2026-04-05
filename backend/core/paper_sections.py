"""Paper section analysis — splits abstracts into navigable semantic sections."""

import logging
import re

from backend.integrations.supabase_client import get_client

logger = logging.getLogger(__name__)

# Common section patterns in academic abstracts
SECTION_PATTERNS = [
    (r"(?:background|introduction|context)[:\.]?\s*", "Introduction"),
    (r"(?:method(?:s|ology)?|approach|design)[:\.]?\s*", "Methodology"),
    (r"(?:result(?:s)?|findings?|outcome(?:s)?)[:\.]?\s*", "Findings"),
    (r"(?:discussion|analysis|interpretation)[:\.]?\s*", "Discussion"),
    (r"(?:conclusion(?:s)?|implications?|significance)[:\.]?\s*", "Implications"),
    (r"(?:objective(?:s)?|aim(?:s)?|purpose|goal(?:s)?)[:\.]?\s*", "Objectives"),
    (r"(?:literature\s+review|theoretical\s+framework|theory)[:\.]?\s*", "Theory"),
]


def split_abstract_sections(abstract: str) -> list[dict]:
    """Split an abstract into semantic sections.

    Returns [{section: str, text: str, offset: int}]
    """
    if not abstract:
        return [{"section": "Abstract", "text": "", "offset": 0}]

    sections = []
    # Try to detect explicit section markers
    for pattern, section_name in SECTION_PATTERNS:
        for match in re.finditer(pattern, abstract, re.IGNORECASE):
            sections.append({
                "section": section_name,
                "offset": match.start(),
                "marker_end": match.end(),
            })

    if not sections:
        # No explicit markers — split by sentences into rough sections
        sentences = re.split(r'(?<=[.!?])\s+', abstract)
        if len(sentences) <= 2:
            return [{"section": "Abstract", "text": abstract, "offset": 0}]

        # Heuristic: first ~25% = intro, middle ~50% = core, last ~25% = conclusion
        n = len(sentences)
        intro_end = max(1, n // 4)
        conclusion_start = n - max(1, n // 4)

        result = []
        intro_text = " ".join(sentences[:intro_end])
        result.append({"section": "Introduction", "text": intro_text, "offset": 0})

        core_text = " ".join(sentences[intro_end:conclusion_start])
        core_offset = len(intro_text) + 1
        result.append({"section": "Core", "text": core_text, "offset": core_offset})

        conclusion_text = " ".join(sentences[conclusion_start:])
        conclusion_offset = core_offset + len(core_text) + 1
        result.append({"section": "Conclusion", "text": conclusion_text, "offset": conclusion_offset})

        return result

    # Sort by offset and extract text between markers
    sections.sort(key=lambda s: s["offset"])
    result = []
    for i, sec in enumerate(sections):
        start = sec["marker_end"]
        end = sections[i + 1]["offset"] if i + 1 < len(sections) else len(abstract)
        text = abstract[start:end].strip()
        result.append({
            "section": sec["section"],
            "text": text,
            "offset": sec["offset"],
        })

    # Add any text before the first section
    if sections[0]["offset"] > 0:
        preamble = abstract[:sections[0]["offset"]].strip()
        if preamble:
            result.insert(0, {"section": "Preamble", "text": preamble, "offset": 0})

    return result


async def get_paper_sections(paper_id: str) -> dict:
    """Get section map for a paper with concept mappings.

    Returns {paper_id, title, sections: [{section, text, offset, concepts: [{id, name}]}]}
    """
    client = get_client()

    # Get paper
    paper = client.table("papers").select("id, title, abstract").eq("id", paper_id).execute()
    if not paper.data:
        return {"paper_id": paper_id, "title": "Unknown", "sections": []}

    paper_data = paper.data[0]
    abstract = paper_data.get("abstract", "")
    sections = split_abstract_sections(abstract)

    # Get concepts for this paper
    paper_concepts = (
        client.table("paper_concepts")
        .select("concept_id, relevance, concepts(id, name)")
        .eq("paper_id", paper_id)
        .order("relevance", desc=True)
        .execute()
    )

    concepts = []
    for pc in (paper_concepts.data or []):
        c = pc.get("concepts")
        if c:
            concepts.append({"id": c["id"], "name": c["name"], "relevance": pc.get("relevance", 0.5)})

    # Map concepts to sections by checking if concept name appears in section text
    for section in sections:
        section_text = section.get("text", "").lower()
        section["concepts"] = [
            {"id": c["id"], "name": c["name"]}
            for c in concepts
            if c["name"].lower() in section_text
        ]
        # If no direct match, assign top concepts to all sections
        if not section["concepts"] and concepts:
            section["concepts"] = [{"id": c["id"], "name": c["name"]} for c in concepts[:2]]

    return {
        "paper_id": paper_id,
        "title": paper_data.get("title", ""),
        "sections": sections,
        "all_concepts": concepts,
    }
