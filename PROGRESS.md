# Korczak AI — Progress Log

## Project Overview
AI Knowledge Navigator that understands academic knowledge structure deeply and navigates users through it.

**Repo:** github.com/Ntexler/korczak
**MVP Domain:** Anthropology (proof of concept)
**Stack:** FastAPI + Next.js 14 + Supabase (PostgreSQL+pgvector) + Claude API

---

## Current Phase: 1b — Graph Seeding
**Status:** 281 papers seeded, enriched, syllabus generated
**Goal:** Seed 5,000 papers (2,500 anthropology + 2,500 sleep/cognition).

### Phase 1a Progress
- [x] DB schema: 3 migrations (core graph, user graph, validation tables)
- [x] FastAPI backend skeleton (11 routes: health, chat, graph)
- [x] Integration clients: Supabase, Claude API, OpenAlex
- [x] Prompt files: paper_analysis (v2), navigator system prompt
- [x] Next.js frontend skeleton (chat UI, zustand store, API lib)
- [x] Both backend and frontend build successfully
- [x] Supabase project created (bgrdmydbrtnucunbpobl, PostgreSQL 17.6)
- [x] All 3 migrations run — 15 tables live in Supabase
- [x] Supabase client tested — reads/writes working
- [x] FastAPI server boots on port 8000
- [ ] Wire API endpoints to Supabase (will do in Phase 1c)

### Phase 1b Progress
- [x] Seeding pipeline created (`backend/pipeline/seed_graph.py`)
- [x] Two domains configured: anthropology (T10149) + sleep/cognition (T10985)
- [x] Test run: 10 papers seeded (5 anthro + 5 sleep) — 70 concepts, 44 claims, 18 relationships
- [x] Full seeding run: 281 papers, 1,405 concepts, 815 claims, 472 relationships
- [x] Multi-source enrichment pipeline (`backend/pipeline/enrich_sources.py`)
  - Semantic Scholar: 104 papers enriched (citations, influential count, TLDR)
  - CrossRef: 100 papers enriched (publisher, references, metadata verification)
  - Retraction Watch: 100+ papers checked (0 retracted)
  - 14 citation count disagreements detected (OpenAlex vs S2)
- [x] Syllabus generator (`backend/pipeline/generate_syllabus.py`)
  - 20 topic files in `syllabus/` folder (auto-grouped from 140+ subfields)
  - Topics: Anthropological Theory, Indigenous & Decolonial, Environmental, Political, Sleep & Cognition, etc.
- [ ] Continue seeding when credits available
- [ ] Entity resolution (embedding-based dedup)
- [ ] Manual validation: 50 nodes, 100 edges

### Files Created
```
db/migrations/
  001_core_schema.sql      — papers, concepts, claims, entities, controversies, relationships
  002_user_schema.sql      — user_profiles, user_knowledge, conversations, messages
  003_validation_schema.sql — source_evidence, quality_flags, disagreements, source_health

backend/
  main.py, config.py       — FastAPI app with CORS, lifespan
  api/health.py            — GET /api/health
  api/chat.py              — POST /api/chat, WS /api/chat/ws/{id}
  api/graph.py             — GET /api/graph/concepts, /stats, /neighbors
  integrations/supabase_client.py  — CRUD for papers, concepts, relationships
  integrations/claude_client.py    — analyze_paper(), navigate()
  integrations/openalex_client.py  — fetch_papers() with cursor pagination
  prompts/paper_analysis.py        — v2 prompt (Phase 0.5 validated)
  prompts/navigator.py             — Navigator system prompt
  pipeline/seed_graph.py           — OpenAlex → Claude → Supabase seeding
  pipeline/enrich_sources.py       — S2 + CrossRef + Retraction Watch enrichment
  pipeline/generate_syllabus.py    — Auto-generate syllabus files from DB
  requirements.txt

syllabus/
  README.md                        — Index of all topic syllabi
  anthropological_theory__philosophy.md
  indigenous__decolonial_studies.md
  environmental__ecological_anthropology.md
  political_anthropology__power.md
  sleep__cognition_research.md
  ... (20 topic files total)

frontend/
  src/app/page.tsx         — Chat page (Korczak Navigator UI)
  src/components/Chat/     — ChatInput, ChatMessage
  src/stores/chatStore.ts  — Zustand store for chat state
  src/lib/api.ts           — API client functions
```

---

## Phase 0.5 — Test New Papers Analysis
**Status:** PASSED (8.5/10)

- **Prompt iteration**: v1 had paradigm_shift inflation (6/10), flat concept types, no paper classification. v2 fixed all issues.
- **10/10 papers** analyzed successfully, all proper anthropology
- **Result**: 8.5/10 average — PASSED

---

## Completed

### 2026-04-04 — Phase 1b: Graph Seeding (in progress)
- [x] Built seeding pipeline with Claude analysis + Supabase inserts
- [x] Added sleep/cognition domain (T10985)
- [x] Test run: 10 papers → 70 concepts, 44 claims, 18 relationships

### 2026-04-03 — Phase 1a: Infrastructure
- [x] Created DB schema (3 migration files, 15 tables)
- [x] Created FastAPI backend skeleton (11 routes)
- [x] Created integration clients (Supabase, Claude, OpenAlex)
- [x] Created Next.js frontend with chat UI
- [x] Supabase project set up and migrations run
- [x] Both backend and frontend build successfully

### 2026-04-03 — Phase 0.5: New Papers Test
- [x] Created `test_new_papers.py` script
- [x] Configured OpenAlex API (topic T10149 = Anthropological Studies)
- [x] Ran Claude analysis on 10 papers — 10/10 success
- [x] Improved prompt v2 — paradigm_shift calibrated, paper_type added
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
| 2026-04-03 | No Docker for local dev | PostgreSQL runs natively on Windows, simpler setup |
| 2026-04-03 | Added sleep/cognition domain | User requested; OpenAlex topic T10985 (Sleep & Wakefulness Research, 85K works) |
| 2026-04-03 | 2,500 papers per domain | 5K total (anthropology + sleep), sorted by citations desc |

---

## Phase Roadmap
- [x] Phase 0: Prompt validation (8/10 on canonical works)
- [x] Phase 0.5: Test new papers (8.5/10, prompt v2)
- [x] Phase 1a: Infrastructure (Supabase + FastAPI + Next.js)
- [ ] **Phase 1b: Graph Seeding** ← WE ARE HERE
- [ ] Phase 1b: Graph Seeding (5K papers, entity resolution)
- [ ] Phase 1c: Navigator (context builder, system prompt, chat UI)
- [ ] Phase 1d: Self-Monitoring v1
- [ ] Phase 2: User Testing
- [ ] Phase 3: Tutor + User Graph Layer 1
- [ ] Phase 3.5: User Graph Layer 2 (Personal Context)
- [ ] Phase 4: Differentiation features
- [ ] Phase 4.5: User Graph Layer 3 (Behavioral Patterns)
- [ ] Phase 5: Beta launch
