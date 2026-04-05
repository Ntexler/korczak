# Korczak AI — Progress Log

## Project Overview
AI Knowledge Navigator that understands academic knowledge structure deeply and navigates users through it.

**Repo:** github.com/Ntexler/korczak
**MVP Domain:** Anthropology (proof of concept)
**Stack:** FastAPI + Next.js 14 + Supabase (PostgreSQL+pgvector) + Claude API

---

## Current Phase: 6.0 — Knowledge Liberation & Map Depth
**Status:** All 3 features implemented — Rich Map Nodes, Connection Transparency, Paper Translation
**Goal:** Make the knowledge map deeply informative, transparent in its reasoning, and accessible across languages.

### Phase 6.2 — Rich Knowledge Map Nodes (COMPLETE)
- [x] Backend: concept_enricher.py — get_concept_with_context (key papers, claims), get_enriched_neighbors (explanations), get_enriched_graph_data
- [x] Graph API returns full context per concept (key_papers, key_claims fields)
- [x] Neighbors endpoint exposes relationship_explanation from DB RPC
- [x] Visualization endpoint includes definitions + explanations + source papers per edge
- [x] Frontend: Knowledge Map info panel widened (w-96), shows definition paragraph, paper count, connection explanations, source paper references
- [x] Frontend: Concept Detail panel — new Key Papers section, Key Claims section, connection explanations in related list
- [x] i18n: 5 new EN/HE pairs (keyPapers, keyClaims, exploreInDepth, source, whyConnected)

### Phase 6.3 — Connection Transparency (COMPLETE)
- [x] DB Migration 012: connection_feedback + proposed_connections tables
- [x] Backend: connection_feedback.py router — agree/disagree on connections, propose missing connections, vote on proposals
- [x] Auto-adjusts connection confidence when community disagrees (>60% threshold, min confidence 0.1)
- [x] Frontend: ConnectionFeedback.tsx — inline agree/disagree + comment buttons on each connection
- [x] API: 5 new connection feedback endpoints + 5 frontend API functions
- [x] Registered at /api/connections (10th router)
- [x] i18n: 6 new EN/HE pairs (agree, disagree, feedback, propose, etc.)

### Phase 6.1 — Paper Translation Pipeline (COMPLETE)
- [x] DB Migration 013: paper_translations table (cached per language, unique per paper+target)
- [x] Backend: paper_translator.py — detect_language (25 languages, script-based), translate via Claude API, cache in DB, flag poor quality
- [x] Backend: translation.py router — POST /translate, GET /{paper_id}, POST /flag, GET /languages/supported
- [x] Frontend: TranslateButton.tsx — one-click translate on any paper card
- [x] Frontend: TranslatedView.tsx — side-by-side original/translated with toggle + flag
- [x] API: 4 new translation endpoints + 4 frontend API functions
- [x] Registered at /api/translation (11th router)
- [x] i18n: 6 new EN/HE pairs (translate, translated, showOriginal, flag, etc.)

### Phase 6 Summary
- **2 DB migrations** (012-013): 3 new tables
- **11 API routers** registered in main.py (was 9)
- **2 new backend API modules**: connection_feedback, translation
- **1 new backend core module**: concept_enricher, paper_translator
- **3 new frontend components**: ConnectionFeedback, TranslateButton, TranslatedView
- **~14 new API functions** in api.ts
- **~23 new i18n strings** (EN/HE)

---

## Previous Phase: 5.0 — Study/Research Platform Expansion
**Status:** All 5 expansion phases implemented — Paper Library, Highlights/Reading Mode, Syllabus, Community, Knowledge Tree
**Goal:** Transform Korczak from a knowledge navigator into a full study/research platform.

### Phase 5 Expansion — Paper Library + Smart Recommendations (COMPLETE)
- [x] DB Migration 006: user_papers, reading_lists, reading_list_papers tables
- [x] Backend: `/api/library` router — CRUD for papers, lists, recommendations
- [x] Smart Reading Recommender: interest profile from saved papers, context-weighted (browsing vs search vs syllabus)
- [x] Context Builder: get_library_context() distinguishes task-driven vs genuine interests
- [x] Chat API: library context injected into Claude prompts
- [x] Frontend: libraryStore (Zustand), PaperLibrary panel, PaperCard, SavePaperButton, ReadingListManager, RecommendationFeed
- [x] API: 10 new library endpoints, i18n: ~20 EN/HE pairs
- [x] Page: Library button in header, toggles between sidebar and library panel

### Phase 5 Expansion — Highlights, Annotations & Reading Mode (COMPLETE)
- [x] DB Migration 007: highlights, learning_paths, learning_path_items, reading_sessions tables
- [x] Backend: `/api/highlights` router — CRUD for highlights, learning paths, items
- [x] Backend: `/api/reading` router — session tracking, analytics, paper sections
- [x] Paper Sections engine: splits abstracts into semantic sections, maps concepts per section
- [x] Context Builder: get_highlight_context() + get_reading_behavior_context() for Claude prompts
- [x] Frontend: highlightStore, readingStore, TextHighlighter (floating toolbar), HighlightOverlay, LearningPathPanel, HighlightSidebar
- [x] Reading Mode: full-screen reader with section nav, concept tags, heartbeat timer (30s intervals)
- [x] API: 12 new endpoints, i18n: ~14 EN/HE pairs

### Phase 5 Expansion — Syllabus Integration (COMPLETE)
- [x] DB Migration 008: syllabi, syllabus_readings, user_syllabi tables
- [x] DB Migration 009: get_syllabus_graph() RPC with centrality + user progress
- [x] MIT OCW Client: fetch_departments() (27 depts), fetch_courses(), fetch_course_readings(), match_readings_to_papers()
- [x] OpenStax Client: fetch_books(), fetch_book_chapters() via OpenStax API
- [x] Scrapers: scrape_mit_ocw.py (all departments), scrape_openstax.py (full catalog)
- [x] Backend: `/api/syllabus` router — browse, detail, fork, user syllabi, custom create, progress tracking
- [x] Context Builder: get_syllabus_context() — where user is in curriculum
- [x] Frontend: SyllabusBrowser, SyllabusDetail, SyllabusProgress (Where Am I), MySyllabi
- [x] API: 7 new endpoints, i18n: ~14 EN/HE pairs

### Phase 5 Expansion — Community Layer (COMPLETE)
- [x] DB Migration 010: paper_comments (threaded), community_votes tables
- [x] Backend: `/api/community` router — threaded comments, voting (upvote/downvote/flag with toggle), public highlights
- [x] Frontend: PaperComments (threaded), SharedHighlights, VoteButton (reusable)
- [x] API: 4 new endpoints, i18n: ~8 EN/HE pairs

### Phase 5 Expansion — Personal Knowledge Tree (COMPLETE)
- [x] DB Migration 011: knowledge_tree_nodes, branch_choices tables
- [x] Centrality engine: compute_concept_centrality(), detect_branch_points(), classify_pillar_vs_niche()
- [x] Knowledge Tree engine: build_user_tree(), get_available_branches(), choose_branch(), get_tree_progress(), refresh_tree()
- [x] Features API: 5 new tree endpoints (tree, choose, branches, progress, visualization/progress)
- [x] Frontend: KnowledgeTree (D3 dendrogram — vertical tree, fog of war, glow effects, zoom/pan)
- [x] BranchChoiceModal: shows paths at fork points with concept counts, paper counts, descriptions
- [x] TreeProgress: summary bar with completion %, depth reached
- [x] Page: Knowledge Tree button in header (visible when user is authenticated)
- [x] API: 4 new endpoints, i18n: ~18 EN/HE pairs

### Expansion Summary
- **6 DB migrations** (006-011): 14 new tables, 1 RPC
- **9 API routers** registered in main.py (was 4)
- **5 new backend API modules**: library, highlights, reading, syllabus, community
- **3 new backend core modules**: reading_recommender, paper_sections, centrality, knowledge_tree
- **2 new integration clients**: MIT OCW, OpenStax
- **2 new pipeline scrapers**: MIT OCW (all depts), OpenStax
- **3 new Zustand stores**: libraryStore, highlightStore, readingStore
- **23 new frontend components** across 6 directories (Library, Highlights, Reading, Syllabus, Community, Tree)
- **~45 new API functions** in api.ts
- **~90 new i18n strings** (EN/HE)
- **Context builder**: 4 new context functions feeding Claude prompts (library, highlights, reading behavior, syllabus)

---

## Previous Phase: 4.5 — User Graph Layer 3 + Polish
**Status:** All 3 user graph layers built, language wired, error handling complete
**Goal:** Behavioral patterns, language-aware responses, robust error handling.

### Phase 3.5 Progress (Personal Context — COMPLETE)
- [x] Context Extractor: regex-based extraction of role, institution, research topic, deadlines, language
- [x] Supports Hebrew patterns (המחקר שלי, סטודנט, etc.)
- [x] Auto-updates user_profiles table from natural conversation
- [x] Rich user context builder: combines Layer 1 (knowledge) + Layer 2 (personal) for system prompts
- [x] Wired into chat API (step 11 — implicit, never asks)

### Phase 4 Progress
- [x] Controversy Mapper: get_controversies(), get_controversy_detail(), map_debate_landscape()
- [x] White Space Finder: orphan concepts, missing connections, low-evidence controversies
- [x] Rising Stars Tracker: trending concepts, rising papers (citation velocity), emerging connections
- [x] Briefing Engine: personalized briefing generation (data + prompt), topic suggestions
- [x] Features API: 8 new endpoints at /api/features/* (controversies, debates, gaps, rising, briefing, visualization)
- [x] D3.js Knowledge Graph: force-directed interactive visualization with zoom, drag, type-colored nodes
- [x] Discovery Panel: collapsible sidebar sections for trending concepts, rising papers, research gaps
- [x] Frontend: Knowledge Map button in header, full-screen graph overlay, discovery panel in sidebar
- [x] i18n: Hebrew + English strings for all new features
- [x] d3 + @types/d3 dependencies installed
- [ ] Briefing generation (needs Claude API credits for actual text)
- [ ] Scheduled briefings (needs cron/deployment infrastructure)

### Phase 4.5 Progress (Behavioral Patterns — COMPLETE)
- [x] Behavior Tracker: session patterns, time-of-day, mode preference, message complexity
- [x] Learning Velocity: concept level progression tracking, interaction counts
- [x] Engagement Profile: comprehensive user analytics (sessions/day, peak hours, complexity)
- [x] Behavior context injected into system prompts (Layer 3)
- [x] Language preference wired: frontend locale → chat API → Claude prompts (HE/EN)
- [x] Error handling: all features API endpoints wrapped in try/except with proper HTTPException
- [x] Engagement API: GET /api/features/engagement/{user_id}
- [x] Migration 005: behavior_data JSONB column on user_profiles
- [ ] Run migration 005 in Supabase SQL Editor (DDL can't run via client)

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

### Phase 3 Progress
- [x] Mode Detector: auto-detect Navigator/Tutor/Briefing from message patterns (7/7 tests pass)
- [x] Level Detector: estimate expertise (child/highschool/student/researcher) from vocabulary + question patterns
- [x] Socratic Tutor prompt: 4 progressive levels (direct → guided → socratic → full socratic)
- [x] Anti-annoyance rules: detect frustration, cap Socratic level, fallback to direct answers
- [x] User Graph Layer 1: implicit knowledge tracking (understanding_level per concept, misconceptions, blind_spots)
- [x] Profile builder: updates user_knowledge table from conversation turns
- [x] Chat API: mode detection + level detection + tutor routing + user graph updates
- [x] Frontend: mode selector (Auto/Navigator/Tutor) in header with icons
- [x] Chat defaults to "auto" mode (auto-detects intent per message)
- [ ] Briefing mode (deferred — needs scheduled jobs + proactive updates)
- [ ] Prerequisite checker (needs more graph data + concept ordering)
- [ ] Test with real users (blocked: API credits)

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
  core/mode_detector.py    — Auto-detect Navigator/Tutor/Briefing intent [Phase 3]
  core/level_detector.py   — Expertise estimation (child→researcher) [Phase 3]
  integrations/supabase_client.py  — CRUD + Navigator helpers (conversations, messages) [Phase 1c]
  integrations/claude_client.py    — analyze_paper(), navigate() with multi-turn [Phase 1c]
  integrations/openalex_client.py  — fetch_papers() with cursor pagination
  prompts/paper_analysis.py        — v2 prompt (Phase 0.5 validated)
  prompts/navigator.py             — Navigator system prompt
  prompts/tutor.py                 — Socratic Tutor prompt (4 levels) [Phase 3]
  user/profile_builder.py          — Implicit knowledge tracking + user context [Phase 3]
  pipeline/seed_graph.py           — OpenAlex → Claude → Supabase seeding
  pipeline/enrich_sources.py       — S2 + CrossRef + Retraction Watch enrichment
  pipeline/generate_syllabus.py    — Auto-generate syllabus files from DB
  tests/benchmark_navigator.py     — 20-question benchmark [Phase 1c]
  graph/consistency_checker.py     — Orphan/dupe/dangling/contradiction detection + auto-fix [Phase 1d]
  graph/pipeline_health.py         — External API health + data freshness + enrichment coverage [Phase 1d]
  graph/quality_monitor.py         — Concept grounding + insight rate + response completeness [Phase 1d]
  graph/cost_monitor.py            — Token estimation + daily breakdown + budget alerts [Phase 1d]
  user/context_extractor.py        — Personal context extraction (role, institution, topic) [Phase 3.5]
  core/controversy_mapper.py       — Controversy sides, evidence, debate landscape [Phase 4]
  core/white_space_finder.py       — Research gaps: orphans, missing connections [Phase 4]
  core/rising_stars.py             — Trending concepts, rising papers, emerging connections [Phase 4]
  core/briefing_engine.py          — Personalized briefing generation + topic suggestions [Phase 4]
  api/features.py                  — 9 endpoints: controversies, debates, gaps, rising, briefing, engagement, visualization [Phase 4+4.5]
  user/behavior_tracker.py         — Session patterns, learning velocity, engagement profile [Phase 4.5]
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
  src/components/Graph/KnowledgeGraph.tsx — D3.js force-directed interactive graph [Phase 4]
  src/components/Discovery/DiscoveryPanel.tsx — Rising stars + research gaps sidebar [Phase 4]
```

---

## Phase 0.5 — Test New Papers Analysis
**Status:** PASSED (8.5/10)

- **Prompt iteration**: v1 had paradigm_shift inflation (6/10), flat concept types, no paper classification. v2 fixed all issues.
- **10/10 papers** analyzed successfully, all proper anthropology
- **Result**: 8.5/10 average — PASSED

---

## Completed

### 2026-04-05 — Phase 8: Timeline of Knowledge
- [x] DB Migration 015: concept_history, graph_changelog, field_milestones tables
- [x] Backend: timeline.py router — concept timeline, field evolution, changelog, milestones
- [x] Frontend: KnowledgeTimeline.tsx — D3.js area chart, milestone markers, playback animation
- [x] Timeline button in main header (Clock icon)
- [x] 4 new API functions, 14th router registered

### 2026-04-05 — Phase 7: Academic Social Network
- [x] DB Migration 014: 8 new tables (researcher_profiles, follows, concept_summaries, summary_versions, summary_votes, discussions, discussion_votes, activity_feed)
- [x] Backend: researcher.py (profiles, follows, activity feed, search — 9 endpoints)
- [x] Backend: summaries.py (concept summaries w/ versioning, discussions w/ threading — 9 endpoints)
- [x] Reputation system (+5 summaries, +2 discussions)
- [x] Frontend: ConceptSummaries.tsx, DiscussionThread.tsx — wired into ConceptDetail panel
- [x] 14 new API functions, 16 new i18n strings, 2 new routers (12th + 13th)

### 2026-04-05 — Phase 6: Knowledge Liberation & Map Depth
- [x] Rich Knowledge Map: concept definitions, key papers, key claims in info panel
- [x] Connection Transparency: explanations, source papers, agree/disagree feedback
- [x] Paper Translation: 25 languages, Claude-powered, cached, side-by-side view
- [x] Connection Feedback system: propose missing connections, community voting
- [x] 2 new DB migrations (012-013), 3 new tables
- [x] 2 new backend routers, 2 new core modules
- [x] 3 new frontend components, ~14 new API functions, ~23 new i18n strings

### 2026-04-05 — Phase 4.5: Behavioral Patterns + Polish
- [x] Behavior Tracker (User Graph Layer 3): session patterns, learning velocity, engagement
- [x] Language preference: locale passed from frontend → chat API → Claude prompts
- [x] Error handling: all features API endpoints wrapped in try/except
- [x] Engagement API endpoint: GET /api/features/engagement/{user_id}
- [x] Migration 005: behavior_data JSONB column

### 2026-04-04 — Phase 3.5 + 4: Personal Context + Differentiation Features
- [x] Context Extractor (User Graph Layer 2): role, institution, research topic, deadlines, language
- [x] Controversy Mapper: sides, evidence, debate landscape
- [x] White Space Finder: orphan concepts, missing connections, low-evidence controversies
- [x] Rising Stars Tracker: trending concepts, citation velocity, emerging connections
- [x] Briefing Engine: personalized briefing data + prompt generation
- [x] Features API: 8 new endpoints (controversies, debates, gaps, rising, briefing, visualization)
- [x] D3.js Knowledge Graph: force-directed interactive visualization (zoom, drag, type colors)
- [x] Discovery Panel: collapsible sidebar with trending, rising papers, research gaps
- [x] Knowledge Map: full-screen graph overlay with legend and controls
- [x] Context extractor wired into chat API (implicit Layer 2 updates)
- [x] Dependencies: d3, @types/d3

### 2026-04-04 — Phase 3: Tutor + User Graph Layer 1
- [x] Mode detector (auto-detect Navigator/Tutor/Briefing from message patterns)
- [x] Level detector (child/highschool/student/researcher from vocabulary)
- [x] Socratic Tutor (4 levels: direct → full Socratic, anti-annoyance rules)
- [x] User Graph Layer 1 (implicit knowledge tracking per concept)
- [x] Profile builder (updates from conversation turns)
- [x] Frontend mode selector (Auto/Navigator/Tutor toggle)

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
- [x] Phase 1d: Self-Monitoring v1
- [ ] Phase 2: User Testing (deferred — needs API credits + deployment)
- [x] Phase 3: Tutor + User Graph Layer 1
- [x] Phase 3.5: User Graph Layer 2 (Personal Context)
- [x] Phase 4: Differentiation Features
- [x] Phase 4.5: User Graph Layer 3 (Behavioral Patterns)
- [x] Phase 5: Study/Research Platform (Library, Highlights, Syllabus, Community, Knowledge Tree)
- [x] **Phase 6: Knowledge Liberation (Rich Map, Transparency, Translation)** ← JUST COMPLETED
- [ ] Phase 7: Academic Social Network (profiles, summaries, collaborative editing)
- [ ] Phase 8: Timeline of Knowledge (evolution tracking, animated history)
- [ ] Phase 9: Advanced Visualization (multiple views, lenses, overlays)
