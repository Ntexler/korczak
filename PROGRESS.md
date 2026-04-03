# Korczak AI — Progress Log

## Project Overview
AI Knowledge Navigator that understands academic knowledge structure deeply and navigates users through it.

**Repo:** github.com/Ntexler/korczak
**MVP Domain:** Anthropology (proof of concept)
**Stack:** FastAPI + Next.js 14 + Supabase (PostgreSQL+pgvector) + Claude API

---

## Current Phase: 0.5 — Test New Papers Analysis
**Status:** PASSED (8.5/10)
**Goal:** Verify Claude can analyze recent (2024-2025) papers as well as canonical ones.

### Phase 0.5 Results
- **Script**: `test_new_papers.py` — fetches from OpenAlex, analyzes with Claude (Sonnet)
- **Results file**: `phase05_results.json`
- **Papers tested**: 10 recent (2024-2025) anthropology articles from OpenAlex topic `T10149`
- **Success rate**: 10/10 analyses parsed successfully
- **Papers analyzed**:
  1. The Disappearance of Rituals (Reklis, 2024)
  2. Decolonial research methodology (2024)
  3. When decolonization is hijacked (2024)
  4. Decolonising Research for Justice (2024)
  5. Transculturality and the Eco-Logic of Memory (2024)
  6. Decolonizing biodiversity conservation (2024)
  7. Ethical futures in biological anthropology (2024)
  8. Endogenous Colonial Borders (Paine et al., 2024)
  9. Doing migration studies with an accent (2024)
  10. Refusal (and Repair) (2024)
- **Quality observations**:
  - Concept extraction: Good — identifies 4-7 concepts per paper with types and novelty
  - Relationship mapping: Good — correctly uses BUILDS_ON, CONTRADICTS, EXTENDS, APPLIES
  - Claims: Solid — distinguishes evidence types and strength
  - Cross-references: Claude connects to known works (Barthes, colonial studies, etc.)
  - Issue: "paradigm_shift" flagged too often (6/10) — may need prompt calibration
- **Prompt iteration**: v1 had paradigm_shift inflation (6/10), flat concept types, no paper classification. v2 fixed all issues.
- **Result**: 8.5/10 average — PASSED. Proceeding to Phase 1a.

---

## Completed

### 2026-04-03 — Phase 0.5: New Papers Test
- [x] Created `test_new_papers.py` script
- [x] Configured OpenAlex API (topic T10149 = Anthropological Studies)
- [x] Ran Claude analysis on 10 papers — 10/10 success
- [x] Saved results to `phase05_results.json`

### 2026-04-03 — Project Setup
- [x] Read all 7 spec documents (5 PDFs + 2 markdown files)
- [x] Initialized git repo
- [x] Created GitHub repo (Ntexler/korczak)
- [x] Created PROGRESS.md
- [x] Created .gitignore

---

## Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| Pre-project | PostgreSQL + pgvector, not Neo4j | Simpler, cheaper, sufficient for 50K nodes |
| Pre-project | Claude API with abstraction layer | Proven good at academic analysis, swap models later |
| Pre-project | Anthropology as MVP domain | Rich controversies, interdisciplinary, good graph test |
| Pre-project | No syllabi in MVP | No public API, defer to Phase 2 |
| Pre-project | Bilingual (HE/EN) | AI responds in user's language, technical terms in English |
| Pre-project | Multi-source validation | 7+ sources, dual-LLM, cross-validation, disagreements as features |
| 2026-04-03 | OpenAlex topic T10149 for anthropology | Concept-based filtering was too broad; topic gives clean anthropology results |
| 2026-04-03 | Claude Sonnet for paper analysis | Good quality/cost tradeoff for batch analysis |
| 2026-04-03 | Improved prompt v2 | Added paper_type, calibrated paradigm_shift, varied concept types, confidence bounds |

---

## Phase Roadmap
- [x] Phase 0: Prompt validation (8/10 on canonical works)
- [x] Phase 0.5: Test new papers (8.5/10, prompt v2)
- [ ] **Phase 1a: Infrastructure** ← WE ARE HERE
- [ ] Phase 1a: Infrastructure (Supabase, FastAPI, Next.js skeletons)
- [ ] Phase 1b: Graph Seeding (5K papers, entity resolution)
- [ ] Phase 1c: Navigator (context builder, system prompt, chat UI)
- [ ] Phase 1d: Self-Monitoring v1
- [ ] Phase 2: User Testing
- [ ] Phase 3: Tutor + User Graph Layer 1
- [ ] Phase 3.5: User Graph Layer 2 (Personal Context)
- [ ] Phase 4: Differentiation features
- [ ] Phase 4.5: User Graph Layer 3 (Behavioral Patterns)
- [ ] Phase 5: Beta launch
