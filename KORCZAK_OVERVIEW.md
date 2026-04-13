# Korczak AI — Knowledge Navigator for Academic Research

## Vision

Korczak transforms academic knowledge from isolated papers into a living, connected landscape. Named after Janusz Korczak — the educator who believed knowledge should be accessible to everyone — the platform helps researchers, students, and curious minds navigate complex academic fields with the guidance of AI.

**The core problem**: Academic knowledge is fragmented across millions of papers. A researcher entering a new field faces weeks of confusion before understanding how concepts connect, what's debated, and where the gaps are.

**Korczak's answer**: An intelligent knowledge graph that maps concepts, claims, papers, and their relationships — then guides users through it with adaptive explanations, active learning, and real-time evidence tracking.

---

## What Korczak Does

### For Learners
- **Learn any academic field from zero** — structured syllabus with week-by-week concept progression
- **Depth slider** — adjust explanations from high school to PhD level in real-time
- **Active recall quiz** — auto-generated questions from the knowledge graph (definition, distinction, evidence, connection types)
- **Fog of war** — visual map showing what you know, what you're learning, and what's unexplored
- **Knowledge tree** — personal learning path with branching choices

### For Researchers
- **Intelligent search** — 5-stage pipeline: query analysis → parallel retrieval → coverage check → synthesis → adversarial skeptic review
- **Inline evidence map** — every claim shows support/contradict counts, debate status, and contradicting evidence
- **Controversy mapping** — see both sides of active debates with evidence
- **Research gap detection** — orphan concepts, missing connections, low-evidence areas
- **Rising stars** — trending concepts, emerging papers, new connections

### For Everyone
- **Knowledge graph visualization** — 5 views (Force, Hierarchical, Radial, Geographic, Sankey) × 5 analytical lenses (Confidence, Recency, Controversy, Community, Gaps)
- **Paper library** — save, tag, rate, organize papers with smart recommendations
- **Translation** — read any paper in 25 languages via Claude
- **Community** — discussions, concept summaries, researcher profiles, voting
- **Daily briefings** — personalized research updates

---

## How Korczak is Different

| Feature | Semantic Scholar | Connected Papers | Elicit | ChatGPT | **Korczak** |
|---------|-----------------|------------------|--------|---------|-------------|
| Paper search | Great | Good | Good | OK | Good |
| Citation graph | Good | Great | No | No | Good |
| **Learn a field from zero** | No | No | No | No | **Yes** |
| **Adaptive depth** | No | No | No | No | **Yes (5 levels)** |
| **Evidence map on claims** | No | No | Partial | No | **Yes (inline)** |
| **Active recall quiz** | No | No | No | No | **Yes** |
| **Knowledge fog of war** | No | No | No | No | **Yes** |
| **Controversy detection** | No | No | No | No | **Yes** |
| Multilingual | Partial | No | No | Yes | **Yes (25 langs)** |
| **Obsidian/Anki/Zotero** | No | No | No | No | **Yes** |

**Korczak's unique position**: The only tool that helps you **understand** a field, not just **search** it. It's the difference between a GPS and a map — both show geography, but only one guides you step by step.

---

## Architecture

### Stack
- **Backend**: FastAPI (Python) — 20 API routers, 12 core modules, 5 integrations
- **Frontend**: Next.js 14 (TypeScript) — 18 component directories, Zustand stores, D3.js visualizations
- **Database**: Supabase (PostgreSQL + pgvector) — 21 migrations, full-text + semantic search
- **AI**: Claude API (Sonnet + Haiku) — smart model routing for cost optimization
- **Search**: Perplexity sonar-pro for web retrieval, OpenAI text-embedding-3-small for semantic search
- **Data**: OpenAlex API for paper metadata, university scrapers for syllabi

### Backend Modules (10,400+ lines Python)

**API Routers** (20):
`chat`, `graph`, `features`, `library`, `highlights`, `reading`, `syllabus`, `community`, `connection_feedback`, `translation`, `researcher`, `summaries`, `timeline`, `upload`, `courses`, `briefings`, `obsidian`, `active_learning`, `plugins`, `health`

**Core Engines** (12):
- `concept_enricher` — rich context assembly (papers, claims, neighbors)
- `context_builder` — keyword extraction, graph context for Claude
- `mode_detector` — auto-detect Navigator/Tutor/Briefing intent
- `level_detector` — expertise level estimation
- `controversy_mapper` — debate landscape analysis
- `white_space_finder` — research gap detection
- `rising_stars` — trending concept detection
- `briefing_engine` — personalized briefing generation
- `active_learning` — evidence map, depth explanations, quiz generation
- `vault_parser` — Obsidian Markdown parsing
- `vault_analyzer` — note-to-concept mapping, gap/connection analysis
- `attention_engine` — signal processing without changing global scores
- `anki_exporter` — flashcard deck generation
- `obsidian_exporter` — Markdown + ZIP export

**Integrations** (5):
- `supabase_client` — database CRUD + RPC functions
- `claude_client` — Claude API with multi-turn, token tracking
- `openalex_client` — paper fetching with cursor pagination
- `openai_client` — embedding generation
- `zotero_client` — Zotero Web API v3 library import

**Search Pipeline** (5 stages):
1. Query Analysis (Haiku) — intent, concepts, sub-queries
2. Parallel Retrieval — semantic, graph, citations, user context, controversies
3. Coverage Check (Haiku) — gap detection, up to 2 retries
4. Synthesis (Sonnet) — mode-aware response with inline sources
5. Skeptic Review (Sonnet) — flags overconfidence, missing perspectives

### Frontend Components (67 TypeScript files)

**Core Views**: FieldCatalog (home) → FieldView (3-panel: syllabus + content + chat) → ConceptDetail (slide-in panel)

**Visualization**: 5 graph views + 5 analytical lenses, all modular and pluggable

**Learning**: ContentPanel with depth slider, evidence map, quiz mode, feedback buttons

**Integration UI**: VaultUpload (drag-and-drop), InsightsPanel (gaps/connections/mappings), export buttons for Obsidian/Anki

### Database (21 migrations, 25+ tables)

**Knowledge Graph**: papers, concepts, claims, entities, relationships, paper_concepts, controversies

**User & Learning**: user_profiles, user_knowledge, conversations, messages, highlights, learning_paths, reading_sessions

**Community**: researcher_profiles, concept_summaries, discussions, paper_comments, community_votes

**Integration**: vault_analyses, vault_note_mappings, attention_signals, vault_insights, paper_translations, connection_feedback

---

## Integrations

### Active (Built)

| Integration | Direction | What it does |
|------------|-----------|--------------|
| **Obsidian** | Bidirectional | Export concepts/fields as Markdown with [[wikilinks]]; Import vault ZIP for gap detection and hidden connection discovery |
| **Anki** | Export | Generate tagged flashcard decks (TSV) with 4 question types |
| **Zotero** | Import | Fetch user library via API, match papers by DOI/title, calculate concept coverage |
| **Browser Extension** | API ready | Lookup papers by DOI/title, get concepts/claims/evidence; flag papers for attention |
| **OpenAlex** | Import | Paper metadata, citations, author data |
| **Perplexity** | Search | Web search retrieval in search pipeline |
| **Claude API** | Core | All AI features — explanations, analysis, synthesis, review |

### Planned

| Integration | Value |
|------------|-------|
| **Notion** | Import notes for vault analysis (larger audience than Obsidian) |
| **Hypothesis** | Pull web annotations on papers for community insights |
| **Overleaf** | Citation suggestions and claim verification during paper writing |
| **Google Scholar** | Alert integration for new papers in user's interests |

---

## Data Sources

### Current
- **OpenAlex**: Primary paper metadata source — titles, authors, abstracts, citations, DOIs
- **University scrapers**: 21 universities across US, UK, Europe, Asia, Israel, Australia — scrape course catalogs for syllabus data
- **MIT OCW + OpenStax**: Open courseware syllabi integration
- **User uploads**: PDF upload pipeline with quality gate (auto-extract metadata, DOI lookup, deduplication)

### MVP Data
- **281 papers** in Anthropology (proof of concept)
- **~1,400 concepts** mapped from those papers
- **~800 claims** extracted with evidence type and strength
- **~470 relationships** between concepts (typed: BUILDS_ON, CONTRADICTS, EXTENDS, etc.)

---

## Active Learning Features

### Depth Slider (1-5)
| Level | Label | Model | Style |
|-------|-------|-------|-------|
| 1 | High School | Haiku | Simple words, everyday analogies, no jargon |
| 2 | Undergrad | Haiku | Basic academic terms with explanations, one example |
| 3 | Advanced | Haiku | Proper terminology, key thinkers, methodological debates |
| 4 | Graduate | Sonnet | Nuances, ongoing debates, cross-field connections |
| 5 | Expert | Sonnet | Cutting-edge debates, unresolved questions, dense |

### Evidence Map (per claim)
- **Status badges**: Well Supported, Supported, Actively Debated, Challenged, Single Source
- **Counts**: support_count, contradict_count
- **Expandable**: click to see contradicting claim texts
- **Inline**: appears directly on every claim, no separate panel

### Quiz Mode
- 6 question types: definition, distinction, evidence, application, connection, critique
- Generated from actual knowledge graph data (concepts, relationships, claims)
- Hint system with reveal-answer flow
- "Ask Korczak" follow-up button on each question

---

## Attention Signal System

A key design principle: **user signals influence investigation, not scores.**

When users interact (save paper, import vault, flag for review), Korczak creates attention signals but **never changes global confidence scores**. Instead:

1. Signals are created (interest / skepticism / neutral)
2. Korczak investigates — finds related papers, contradictions, recent work
3. Findings are reported back to the user
4. User decides what to do with the information

This prevents the "crowd-sourced truth" problem where popular opinions override scientific evidence.

---

## i18n

Full Hebrew + English bilingual support throughout the application:
- ~200+ translated strings
- RTL layout support for Hebrew
- Font families: Assistant (display), Geist (body)
- All new features (vault insights, quiz, evidence map) include Hebrew labels

---

## Cost Optimization

- **Smart model routing**: Haiku for fast/cheap operations (query analysis, coverage check, depth 1-3 explanations), Sonnet for quality-critical operations (synthesis, review, depth 4-5)
- **Conditional skeptic**: Only runs skeptic review when confidence warrants it
- **Caching**: TTL cache on embeddings, query analysis, full search results
- **Batch operations**: Concept enrichment, paper analysis run in batches

---

## Project Stats

- **54 commits** across 12 development phases
- **96 Python files** (backend)
- **67 TypeScript files** (frontend)
- **21 SQL migrations**
- **10,400+ lines** of backend core + API code
- **20 API routers** with 80+ endpoints
- **7 integrations** (Obsidian, Anki, Zotero, Browser Extension, OpenAlex, Perplexity, Claude)
