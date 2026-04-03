# Korczak AI — Progress Log

## Project Overview
AI Knowledge Navigator that understands academic knowledge structure deeply and navigates users through it.

**Repo:** github.com/Ntexler/korczak
**MVP Domain:** Anthropology (proof of concept)
**Stack:** FastAPI + Next.js 14 + Supabase (PostgreSQL+pgvector) + Claude API

---

## Current Phase: 0.5 — Test New Papers Analysis
**Status:** Starting
**Goal:** Verify Claude can analyze recent (2024-2025) papers as well as canonical ones.

---

## Completed

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

---

## Phase Roadmap
- [x] Phase 0: Prompt validation (8/10 on canonical works)
- [ ] **Phase 0.5: Test new papers** ← WE ARE HERE
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
