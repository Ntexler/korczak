"""Paper analysis prompt — v3 (Phase 6.5: article-grounded claims).

v3 adds provenance fields to CLAIMS extraction:
  - category: main | supporting | background | limitation
  - verbatim_quote: direct passage from the source supporting the claim
      (when working from full text, this is a true verbatim passage;
       when working from abstract only, this is the abstract sentence the
       claim came from — the author's own summary wording, not a raw source quote)
  - quote_location: where the quote appears (section / paragraph / abstract)
  - examples: cases / data / figures the author uses to illustrate the claim

Claims in the DB should always be traceable to a grounding passage — even
when that passage is abstract-derived. Feature 6.5 (on-demand provenance
extraction) upgrades abstract-derived quotes to full-text quotes when the
user requests them.
"""

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

3. CLAIMS: Central claims with evidence basis and grounding.
   Format: [{{
     "claim": str,
     "evidence_type": "empirical|theoretical|comparative|methodological|meta_analytic",
     "strength": "strong|moderate|weak",
     "testable": bool,
     "category": "main|supporting|background|limitation",
     "verbatim_quote": str,
     "quote_location": str,
     "examples": [{{"text": str, "kind": "case|dataset|figure|table", "location": str}}]
   }}]
   - "testable": can this claim be empirically verified or falsified?
   - "category":
       - "main" = a primary finding / central contribution of the paper
       - "supporting" = secondary evidence or sub-claim that supports a main claim
       - "background" = a claim drawn from prior literature the author is restating
       - "limitation" = an acknowledged caveat or boundary condition on the findings
   - "verbatim_quote": the specific sentence(s) in the ABSTRACT that this claim is derived from (max ~300 chars). Quote the abstract directly — do not rephrase.
   - "quote_location": the string "abstract" for every claim (since you are working from the abstract only).
   - "examples": include only when the abstract explicitly names a case, dataset, figure, or table. Usually empty from an abstract.

4. HISTORICAL_SIGNIFICANCE: Role in the field's development.
   Format: {{"paradigm_shift": bool, "influenced_fields": [str], "controversy_generated": str, "lasting_impact": str}}
   - CRITICAL: "paradigm_shift" should be TRUE only for works that fundamentally redefine how a field thinks (maybe 1-2% of all papers). A good paper with a new perspective is NOT a paradigm shift. When in doubt, set false.
   - "controversy_generated": if no clear controversy, say "none apparent from abstract"

Return ONLY valid JSON with keys: paper_type, concepts, relationships, claims, historical_significance"""


ANALYSIS_PROMPT_FULL_TEXT = """Analyze this academic work for a knowledge graph. You are working from the full text of the paper — extract richer detail and connections than would be possible from an abstract alone. Ground every claim in a specific, verbatim passage from the paper.

WORK: {title}
AUTHORS: {authors}
YEAR: {year}
FULL TEXT: {full_text}

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
   - With full text available, capture more nuanced concepts that may not appear in the abstract.

2. RELATIONSHIPS: How this work connects to other specific works, authors, or intellectual traditions.
   Format: [{{"from": str, "to": str, "type": "BUILDS_ON|CONTRADICTS|EXTENDS|APPLIES|ANALOGOUS_TO|RESPONDS_TO", "confidence": float, "explanation": str}}]
   - With full text, you can identify relationships from the references, literature review, and discussion sections.
   - "confidence": 0.7-0.85 if clearly discussed in the text, 0.85+ if explicitly cited and discussed at length.
   - Name SPECIFIC works or authors referenced in the paper (e.g. "Said's Orientalism" not "postcolonial theory").

3. CLAIMS: Central claims with evidence basis and verbatim grounding.
   Format: [{{
     "claim": str,
     "evidence_type": "empirical|theoretical|comparative|methodological|meta_analytic",
     "strength": "strong|moderate|weak",
     "testable": bool,
     "category": "main|supporting|background|limitation",
     "verbatim_quote": str,
     "quote_location": str,
     "examples": [{{"text": str, "kind": "case|dataset|figure|table", "location": str}}]
   }}]
   - "testable": can this claim be empirically verified or falsified?
   - "category":
       - "main" = a primary finding / central contribution of the paper
       - "supporting" = secondary evidence or sub-claim that supports a main claim
       - "background" = a claim drawn from prior literature the author restates
       - "limitation" = an acknowledged caveat or boundary condition on the findings
   - "verbatim_quote": the exact sentence(s) from the paper that support this claim (max ~300 chars). Reproduce them verbatim — do not paraphrase, do not reword, do not "clean up" spelling or punctuation. If the supporting passage is longer than 300 chars, quote the most load-bearing ~300 chars and use an ellipsis.
   - "quote_location": approximate location in the paper — "Introduction, para 2" / "Results, section 3.1" / "Discussion, page 5" / "Conclusion". Use the section names as they appear in the paper when possible.
   - "examples": include cases, datasets, figures, or tables the author uses to illustrate or support this specific claim. Format: {{"text": <brief description or verbatim quote of the example>, "kind": "case|dataset|figure|table", "location": <where it appears>}}. Empty list if the claim has no distinct examples in the text.
   - Extract claims primarily from Results, Discussion, and Conclusion sections. Literature review claims should be tagged category="background".

4. HISTORICAL_SIGNIFICANCE: Role in the field's development.
   Format: {{"paradigm_shift": bool, "influenced_fields": [str], "controversy_generated": str, "lasting_impact": str}}
   - CRITICAL: "paradigm_shift" should be TRUE only for works that fundamentally redefine how a field thinks (maybe 1-2% of all papers). A good paper with a new perspective is NOT a paradigm shift. When in doubt, set false.
   - "controversy_generated": if no clear controversy, say "none apparent from text"

Return ONLY valid JSON with keys: paper_type, concepts, relationships, claims, historical_significance"""
