"""Context builder — extracts graph context for Navigator responses."""

import re

from backend.integrations import supabase_client as db

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
                authors = p.get("authors", [])
                first_author = authors[0].get("name", "Unknown") if authors else "Unknown"
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
