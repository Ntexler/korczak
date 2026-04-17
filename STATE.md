# Korczak AI — Current State

_Last updated: 2026-04-17. Replace this file (don't append) at the end of each working unit._

## Current phase

**Post-Phase 11 — Course Generation + UX Redesign.** All core phases (1–11) complete. 39 AI-generated courses across 13 fields. Feature branch merged to main (56 commits). Domain-first UX (FieldCatalog → FieldView → ContentPanel lesson experience) is the current UI model.

## Build status

- Backend: FastAPI, 20+ routers, search pipeline, briefing system, course generation — all operational.
- Frontend: Next.js 16 + D3. Domain-first UI with FieldCatalog home, FieldView 3-panel (syllabus/content/chat), ClaimCard + ProvenancePanel integrated.
- DB: 17,660 papers, 138,789 concepts, 40,833 relationships, 39 generated courses, 1,579 course readings. Through migration 028.
- Branch: everything on `main`. Old feature branches fully merged.

## Active blockers

🔴 **OpenAI rate limit** — embeddings (text-embedding-3-small) returning 429. Entity Resolution dedup blocked. Semantic retriever in search pipeline also affected.
🟡 **Auth** — still using mock `userId = "demo-researcher-1"`. Blocks: real user progress tracking, personal overlay, deployment to real users.
🟡 **Briefings table** — migration 020 applied but `user_id` column is UUID; mock user ID is a string. Generation works with user_id=None.

## Next 3 concrete steps

1. **Entity Resolution** — when OpenAI quota resets, run `python -m backend.pipeline.entity_resolution --merge`. Dedup 138K concepts → eliminate duplicates.
2. **Hume EVI** — voice interface integration. SDK: `pip install hume`. WebSocket-based, emotion-aware.
3. **Auth + Deployment** — Supabase Auth → Vercel (frontend) + Railway (backend). Last step before real users.

## Last decision

**2026-04-17:** Deferred entity resolution (OpenAI 429). Completed: ClaimCard in ChatMessage, briefing system, 39 courses generated, branch merge to main.

## Where to look (shortcuts)

| Need | File |
|---|---|
| Roadmap details for any 6.x feature | `docs/spec/roadmap.md` |
| Architecture / modules / DB tables | `docs/spec/overview.md` |
| Search pipeline internals | `docs/spec/pipeline.md` |
| Provenance schema (claims/papers/authors) | migrations 024–026, `FEATURE_6_5_DEPLOY.md` |
| Course generation | `backend/pipeline/generate_field_courses.py` |
| Briefing system | `backend/pipeline/briefing_scheduler.py` + `backend/api/briefings.py` |
| Entity resolution | `backend/pipeline/entity_resolution.py` |
| What was done when | `PROGRESS.md` (read only on request) |
