# Korczak AI — Progress Log

## Project Overview
AI Knowledge Navigator that understands academic knowledge structure deeply and navigates users through it.

**Repo:** github.com/Ntexler/korczak
**MVP Domain:** Anthropology (proof of concept)
**Stack:** FastAPI + Next.js 14 + Supabase (PostgreSQL+pgvector) + Claude API

---

## Current Phase: 1d — Self-Monitoring v1
**Status:** All monitors built and running, health dashboard deployed
**Goal:** Production-ready observability before user testing.

### Phase 1d Progress
- [x] Consistency checker: orphan detection, duplicates, dangling rels, circular contradictions, confidence anomalies, stale concepts
- [x] Pipeline health monitor: external API pings (OpenAlex, S2, CrossRef), data freshness, enrichment coverage
- [x] Navigator quality monitor: concept grounding check, insight rate, empty response detection
- [x] Cost monitor: token estimation, daily breakdown, monthly rate projection, budget alerts
- [x] Health API: GET /api/health/detailed aggregates all monitors
- [x] Frontend: SystemHealth widget in sidebar (graph issues, API status, cost estimate)
- [x] Graph cleanup: removed 255 dangling relationships (auto-fix)
- [x] Graph status: HEALTHY (0 critical, 2 medium: 173 orphans, 362 missing definitions)
- [ ] Schedule monitors to run automatically (cron/Airflow — deferred to deployment)
- [ ] Confidence decay (relationships not reinforced in 2+ years) — deferred to production

---

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
- [x] Wire API endpoints to Supabase (done in Phase 1c)

### Phase 1c Progress (COMPLETE)
- [x] SQL RPC: `get_concept_neighborhood()` recursive CTE for graph traversal
- [x] Context builder: keyword extraction (Hebrew-aware), concept search, papers/claims/neighborhood lookup
- [x] Claude client: multi-turn conversation support with history
- [x] Supabase helpers: papers_for_concept, claims, controversies, conversations, messages
- [x] Chat API: full pipeline (create conversation → save message → build context → navigate → extract insight → respond)
- [x] Graph API: all 4 endpoints wired to real Supabase queries
- [x] Dark museum theme: "Late-night library with a brilliant guide" (warm gold/amber on deep charcoal)
- [x] 3-panel layout: Knowledge Sidebar (280px) | Chat (flex) | Concept Detail (320px, toggleable)
- [x] Welcome screen: animated, suggested prompts, graph stats
- [x] Chat redesign: animated messages (framer-motion), concept badges, insight callouts
- [x] Knowledge sidebar: graph stats dashboard, topic browser (16 topics), recent concepts
- [x] Concept detail panel: slides in on badge click, shows definition/confidence/neighbors
- [x] 20-question benchmark test with optional Claude-as-judge scoring
- [x] SQL migration 004 applied in Supabase
- [ ] Run benchmark and score >= 15/20 (blocked: API credits depleted)

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

### Files Created/Modified
```
db/migrations/
  001_core_schema.sql      — papers, concepts, claims, entities, controversies, relationships
  002_user_schema.sql      — user_profiles, user_knowledge, conversations, messages
  003_validation_schema.sql — source_evidence, quality_flags, disagreements, source_health
  004_navigator_rpcs.sql   — get_concept_neighborhood() recursive CTE [Phase 1c]

backend/
  main.py, config.py       — FastAPI app with CORS, lifespan
  api/health.py            — GET /api/health
  api/chat.py              — POST /api/chat with full Navigator pipeline [Phase 1c]
  api/graph.py             — GET /api/graph/* wired to Supabase [Phase 1c]
  core/context_builder.py  — Keyword extraction + graph context assembly [Phase 1c]
  integrations/supabase_client.py  — CRUD + Navigator helpers (conversations, messages) [Phase 1c]
  integrations/claude_client.py    — analyze_paper(), navigate() with multi-turn [Phase 1c]
  integrations/openalex_client.py  — fetch_papers() with cursor pagination
  prompts/paper_analysis.py        — v2 prompt (Phase 0.5 validated)
  prompts/navigator.py             — Navigator system prompt
  pipeline/seed_graph.py           — OpenAlex → Claude → Supabase seeding
  pipeline/enrich_sources.py       — S2 + CrossRef + Retraction Watch enrichment
  pipeline/generate_syllabus.py    — Auto-generate syllabus files from DB
  tests/benchmark_navigator.py     — 20-question benchmark [Phase 1c]
  graph/consistency_checker.py     — Orphan/dupe/dangling/contradiction detection + auto-fix [Phase 1d]
  graph/pipeline_health.py         — External API health + data freshness + enrichment coverage [Phase 1d]
  graph/quality_monitor.py         — Concept grounding + insight rate + response completeness [Phase 1d]
  graph/cost_monitor.py            — Token estimation + daily breakdown + budget alerts [Phase 1d]
  requirements.txt

syllabus/
  ... (20 topic files)

frontend/
  src/app/globals.css              — Dark museum theme with custom animations [Phase 1c]
  src/app/layout.tsx               — Korczak metadata + dark class [Phase 1c]
  src/app/page.tsx                 — 3-panel layout: sidebar | chat | concept panel [Phase 1c]
  src/components/Chat/ChatMessage  — Animated bubbles + concept badges + insights [Phase 1c]
  src/components/Chat/ChatInput    — Sleek textarea with compass send button [Phase 1c]
  src/components/Welcome/WelcomeScreen — Animated welcome with suggested prompts [Phase 1c]
  src/components/Sidebar/KnowledgeSidebar — Graph stats + topics + recent concepts [Phase 1c]
  src/components/Sidebar/GraphStats      — Animated metric cards [Phase 1c]
  src/components/Sidebar/TopicBrowser    — 16 browseable topics [Phase 1c]
  src/components/ConceptPanel/ConceptDetail — Slide-in concept details [Phase 1c]
  src/stores/chatStore.ts          — Panel state + graph stats cache [Phase 1c]
  src/lib/api.ts                   — Full API client (chat, graph, history, health) [Phase 1c+1d]
  src/components/Sidebar/SystemHealth.tsx — Health dashboard widget [Phase 1d]
```

---

## Phase 0.5 — Test New Papers Analysis
**Status:** PASSED (8.5/10)

- **Prompt iteration**: v1 had paradigm_shift inflation (6/10), flat concept types, no paper classification. v2 fixed all issues.
- **10/10 papers** analyzed successfully, all proper anthropology
- **Result**: 8.5/10 average — PASSED

---

## Completed

### 2026-04-04 — Phase 1d: Self-Monitoring v1
- [x] Built 4 monitors: consistency checker, pipeline health, quality monitor, cost monitor
- [x] Health API: GET /api/health/detailed aggregates all monitors
- [x] Frontend: SystemHealth widget in sidebar
- [x] Graph cleanup: removed 255 dangling relationships
- [x] Modernized fonts (Assistant for Hebrew, dropped serif headings)
- [x] Improved API error handling (meaningful credit-depleted messages)

### 2026-04-04 — Phase 1c: Navigator + Immersive Frontend
- [x] Backend: Navigator core (context builder, multi-turn Claude, graph-backed chat pipeline)
- [x] Backend: All API endpoints wired to real Supabase queries
- [x] Frontend: Dark museum theme with warm gold/amber accents
- [x] Frontend: 3-panel responsive layout with sidebar, chat, concept detail
- [x] Frontend: Animated messages, concept badges, insight callouts, welcome screen
- [x] Benchmark: 20-question test across 6 categories
- [x] Dependencies: framer-motion, lucide-react, @tailwindcss/typography

### 2026-04-04 — Phase 1b: Graph Seeding
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
- [x] Phase 1b: Graph Seeding (281 papers seeded, enriched, syllabus generated)
- [x] Phase 1c: Navigator + Immersive Frontend
- [x] **Phase 1d: Self-Monitoring v1** ← JUST COMPLETED
- [ ] Phase 2: User Testing
- [ ] Phase 3: Tutor + User Graph Layer 1
- [ ] Phase 3.5: User Graph Layer 2 (Personal Context)
- [ ] Phase 4: Differentiation features
- [ ] Phase 4.5: User Graph Layer 3 (Behavioral Patterns)
- [ ] Phase 5: Beta launch
