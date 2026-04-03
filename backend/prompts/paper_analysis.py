"""Paper analysis prompt — v2 (Phase 0.5 validated)."""

ANALYSIS_PROMPT = """Analyze this academic work for a knowledge graph. You are working from the abstract only — calibrate your confidence accordingly. Do NOT over-interpret or infer beyond what the text supports.

WORK: {title}
AUTHORS: {authors}
YEAR: {year}
ABSTRACT: {abstract}

Extract in JSON:

0. PAPER_TYPE: Classify this paper.
   Format: {{"type": "original_research|review|meta_analysis|theoretical|methodological|commentary|book_chapter", "subfield": str, "summary": str}}
   - "subfield": the specific academic subfield (e.g. "medical anthropology", not just "anthropology")
   - "summary": one sentence describing the paper's core contribution

1. CONCEPTS: Key concepts introduced or central to this work.
   Format: [{{"name": str, "type": "theory|method|framework|phenomenon|tool|metric|critique|paradigm", "definition": str, "novelty_at_time": "high|medium|low", "well_established": bool}}]
   - Use VARIED types — not everything is a "framework". A measurement tool is a "tool", a critique of existing work is a "critique", an observed pattern is a "phenomenon".
   - "well_established": true if this concept existed before this paper and is widely known in the field.
   - "novelty_at_time": "high" ONLY if this paper introduces the concept for the first time. Most concepts in most papers are "low" (using existing ideas) or "medium" (applying known ideas in a new context).

2. RELATIONSHIPS: How this work connects to other specific works, authors, or intellectual traditions.
   Format: [{{"from": str, "to": str, "type": "BUILDS_ON|CONTRADICTS|EXTENDS|APPLIES|ANALOGOUS_TO|RESPONDS_TO", "confidence": float, "explanation": str}}]
   - "confidence": 0.5-0.7 if inferred from abstract context, 0.8+ only if explicitly stated.
   - Prefer naming SPECIFIC works or authors over vague traditions (e.g. "Said's Orientalism" not "postcolonial theory").
   - Only include relationships you can justify from the abstract text.

3. CLAIMS: Central claims with evidence basis.
   Format: [{{"claim": str, "evidence_type": "empirical|theoretical|comparative|methodological|meta_analytic", "strength": "strong|moderate|weak", "testable": bool}}]
   - "testable": can this claim be empirically verified or falsified?

4. HISTORICAL_SIGNIFICANCE: Role in the field's development.
   Format: {{"paradigm_shift": bool, "influenced_fields": [str], "controversy_generated": str, "lasting_impact": str}}
   - CRITICAL: "paradigm_shift" should be TRUE only for works that fundamentally redefine how a field thinks (maybe 1-2% of all papers). A good paper with a new perspective is NOT a paradigm shift. When in doubt, set false.
   - "controversy_generated": if no clear controversy, say "none apparent from abstract"

Return ONLY valid JSON with keys: paper_type, concepts, relationships, claims, historical_significance"""
