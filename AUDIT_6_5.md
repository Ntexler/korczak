# Audit — Feature 6.5: Article-Grounded Claims

Branch: `feature/article-grounded-claims`
Date: 2026-04-14

Pre-build audit of the current data model, pipeline, and UI layers against what Feature 6.5 requires every surfaced claim to show.

---

## Required by 6.5 vs. what exists today

| Field 6.5 requires | Exists? | Where / gap |
|---|---|---|
| Author name | ✅ | `papers.authors[].name` |
| Author institution | ✅ | `papers.authors[].institution` (first institution only, display name, no ROR ID) |
| Author bio / background | ❌ | No column, no JSONB field, no enrichment pipeline |
| Year of publication | ✅ | `papers.publication_year` |
| Country (author / institution) | ❌ | Not captured. `entities.ror_id` column exists but never populated |
| Main claims of paper | ⚠️ partial | `claims.claim_text` exists; no distinction between main / supporting / background / limitation |
| Examples from paper | ❌ | Not extracted, not stored |
| Verbatim quote from source | ❌ | No column on `claims`; Claude prompt does not ask for it |
| Quote location (page / section) | ❌ | No column |
| DOI / article link | ✅ | `papers.doi` present for most |
| Open-access URL | ⚠️ partial | `papers.open_access` bool exists; no actual URL field. Full text exists for ~30–50% via Unpaywall |
| Paywall / access-status indicator | ❌ | No structured field |
| Funding data | ⚠️ defined, empty | `papers.funding JSONB` defined in migration 001 but never populated; OpenAlex `grants` is not requested during seeding |

Legend: ✅ done · ⚠️ partial · ❌ missing

---

## Pipeline findings

### Claude analysis prompts (`backend/prompts/paper_analysis.py`)
- **`ANALYSIS_PROMPT`** (abstract-only, used by `seed_optimized.py`): extracts `paper_type`, `concepts`, `relationships`, `claims`, `historical_significance`. Does **not** request verbatim quotes, examples, author background, or funding.
- **`ANALYSIS_PROMPT_FULL_TEXT`** (used by `seed_deep.py`): says "Ground every claim in specific textual evidence" but the output schema has **no `quote` / `passage` / `example` field**. The instruction is effectively lost at extraction time.

### Seeding pipelines
- `seed_optimized.py` — primary path. Fetches abstract + metadata from OpenAlex. Does **not** request `grants`. Stores author institution but nothing richer.
- `seed_deep.py` — secondary path. Fetches full text via Unpaywall (~30–50% success rate), stores in `papers.full_text`, but prompt isn't updated to extract quotes.
- `seed_foreign.py`, `seed_citations.py` — not relevant to this feature.

### What actually lands in the DB for a claim
```json
{
  "claim": "Decolonization challenges the hegemony of Western knowledge...",
  "evidence_type": "theoretical",
  "strength": "moderate",
  "testable": false
}
```
No quote. No example. No category. No location.

---

## API / frontend findings

- `GET /api/graph/concepts/{id}` returns claims with `claim_text`, `evidence_type`, `strength`, `confidence` only.
- `GET /api/library/papers` selects `id, title, authors, publication_year, cited_by_count, abstract, doi` — no full text, no funding, no claim-level data.
- `ContentPanel.tsx` renders claim text + badges (evidence type, strength) — no provenance block.
- `ChatMessage.tsx` renders markdown + concept badges — no source-grounding module.
- No existing `ClaimCard` / `ProvenancePanel` component.

---

## Recommended migrations for 6.5 (minimal set)

### Migration 024 — extend `claims` with provenance
```sql
ALTER TABLE claims ADD COLUMN IF NOT EXISTS verbatim_quote TEXT;
ALTER TABLE claims ADD COLUMN IF NOT EXISTS quote_location TEXT;   -- "section 3.2", "Results, para 2", etc.
ALTER TABLE claims ADD COLUMN IF NOT EXISTS claim_category TEXT
  CHECK (claim_category IN ('main', 'supporting', 'background', 'limitation'));
ALTER TABLE claims ADD COLUMN IF NOT EXISTS examples JSONB DEFAULT '[]';
-- examples: [{ text, kind: 'case'|'dataset'|'figure'|'table', location }]
```

### Migration 025 — access fields on `papers`
```sql
ALTER TABLE papers ADD COLUMN IF NOT EXISTS access_url TEXT;
ALTER TABLE papers ADD COLUMN IF NOT EXISTS access_status TEXT
  CHECK (access_status IN ('open', 'paywalled', 'hybrid', 'preprint', 'author_copy', 'unknown'));
```

### No migration needed (JSONB extension)
`papers.authors` JSONB — extend schema in code to: `{name, openalex_id, orcid, institution, institution_ror_id, country, bio}`. Populate via an enrichment step, not a migration.

### `papers.funding` already exists
No migration. Need to (a) add `grants` to the OpenAlex fetch, (b) backfill existing rows.

---

## Build plan for 6.5 (proposed order)

### Stage A — Data model + prompt (foundation)
1. Write migration 024 (`claims` provenance columns) and migration 025 (`papers` access fields). Apply to local DB.
2. Update `ANALYSIS_PROMPT_FULL_TEXT` output schema to include `verbatim_quote`, `quote_location`, `claim_category`, `examples`.
3. Update the abstract-only `ANALYSIS_PROMPT` with `claim_category` (quote/examples will be sparse from abstract, that's OK).
4. Update insertion logic in `seed_optimized.py` and `seed_deep.py` to persist the new fields.

### Stage B — Enrichment
5. Add OpenAlex `grants` to the fetch projection; populate `papers.funding` during seeding. Write a one-time backfill script for existing rows.
6. Add ROR lookup for institutions → populate `country` into `papers.authors[]`. Backfill script.
7. Populate `access_url` + `access_status` from Unpaywall response (already fetched; just plumb it through). Backfill script.
8. Author bio: defer to a later sub-stage — it requires a separate OpenAlex authors fetch + Claude-generated summary. Start without it; UI degrades gracefully when missing.

### Stage C — Reanalysis (the cost-heavy step)
9. Run an update pass over papers where `full_text IS NOT NULL`: re-invoke Claude with the new prompt, capture quotes + categories + examples, update `claims` rows. Non-full-text papers get `claim_category` only.

### Stage D — API
10. Extend claim-returning endpoints (concept enricher, library, chat context builder) to include the new fields.
11. New endpoint `GET /api/claims/{id}/provenance` returning the full provenance record.

### Stage E — UI
12. New components: `Claims/ClaimCard.tsx`, `Claims/ProvenancePanel.tsx`.
13. Replace existing claim rendering in `ContentPanel.tsx`, `ChatMessage.tsx`, and lesson views (when 6.4 arrives) with the new components.
14. Design rule: a claim without provenance is not rendered — either full card or not shown.

### Stage F — Quality gate
15. Dashboard query: % of claims that have `verbatim_quote`, % of papers that have `access_url`, % of authors with `country`. Target thresholds before we call 6.5 "done."

---

## Open decisions before Stage A

1. **Scope of first slice**: do we ship Stages A + B + D + E against existing data first (showing what we have, gracefully degrading), and push reanalysis (C) to a second slice? Recommended — it lets us validate the UI before spending Claude tokens on reanalysis.
2. **Reanalysis budget**: how many papers have `full_text`, and are we willing to reanalyze all of them? Needs a count query and a cost check before Stage C.
3. **Author bio — in or out of MVP?** Recommendation: out. It's the lowest-value field per token spent, and UI can show author + institution + country without a bio.
