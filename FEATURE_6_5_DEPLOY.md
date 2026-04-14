# Feature 6.5 — Deployment Guide

Article-Grounded Claims. Built on branch `feature/article-grounded-claims`.
Everything here is idempotent — safe to re-run.

## 1. Apply SQL migrations

```bash
# Apply via psql (or your migration runner of choice)
psql "$SUPABASE_URL" -f db/migrations/024_claim_provenance.sql
psql "$SUPABASE_URL" -f db/migrations/025_paper_access.sql
psql "$SUPABASE_URL" -f db/migrations/026_author_profiles.sql
```

All three use `IF NOT EXISTS` on columns/tables/indexes — safe to re-run
on a partially-migrated DB.

## 2. Environment variables

Required:
- `SUPABASE_URL` / `SUPABASE_SERVICE_KEY` (already set)
- `OPENALEX_EMAIL` (already set; required for Unpaywall in the
  provenance extractor's `unpaywall` source)
- `ANTHROPIC_API_KEY` (already set; required for the aggregator and for
  author bio generation)

Optional — enable extra sources in the provenance extractor:
- `SEMANTIC_SCHOLAR_API_KEY` — raises the rate limit; without it the S2
  source still works for modest traffic.
- `CORE_API_KEY` — enables the `core` source. Without it the source is
  skipped gracefully.

## 3. Backfills

Run in this order for the best experience. All three take `--dry-run`
and support iterative runs (`--limit N`).

### a) Populate access fields (fast, no Claude cost)
```bash
python -m backend.pipeline.backfill_paper_access --limit 500
```
Populates `papers.access_url` + `papers.access_status` via Unpaywall.
Typical first batch of 500 papers completes in a few minutes.

### b) Populate funding + author countries (fast, OpenAlex only)
```bash
python -m backend.pipeline.backfill_paper_funding --limit 500
```
Re-fetches each paper from OpenAlex and writes `papers.funding` JSONB
plus merges `country` + `institution_ror_id` into each authorship's
existing entry in `papers.authors[]`.

### c) Build author profiles (Claude cost for bios)
```bash
# Stub missing profiles + enrich from OpenAlex — cheap
python -m backend.pipeline.backfill_author_profiles --skip-bios --limit 500

# When you're ready to pay for bios (Haiku, ~$0.001 per bio)
python -m backend.pipeline.backfill_author_profiles --enrich-only --limit 500
```
The `--skip-bios` flag does everything except the bio Claude call.
`--enrich-only` reuses existing profile stubs instead of re-scanning
`papers.authors[]`.

## 4. Deploy backend

No config changes needed beyond env vars. The two new routers register
automatically:
- `/api/claims/*`
- `/api/authors/*`

Existing flows (`/api/graph/concepts/:id`, chat context builder,
library list) now include Feature 6.5 columns in every claim payload;
clients that don't read them are unaffected.

## 5. Wire ClaimCard into existing views (UX decision)

The new `frontend/src/components/Claims/` components are ready but not
yet integrated into existing views. Suggested integration points, in
priority order:

- `frontend/src/components/Field/ContentPanel.tsx` — the "Evidence
  claims" list is the prime candidate. Replace the inline rendering
  block (~lines 701–770) with `<ClaimCard claim={claim} />` and you
  get grounding for free.
- `frontend/src/components/Chat/ChatMessage.tsx` — render `ClaimCard`
  wherever claims are embedded in chat replies.
- Concept drawer — similar swap.

This step was deliberately deferred: the integration requires small UX
judgment calls (where does `AuthorProfileDrawer` live in the page
hierarchy? does the card expand inline or in a drawer? etc.) that are
faster to make with the component in hand than to guess at up front.

## 6. Testing the flow end-to-end

Once migrations applied and backend deployed:

```bash
# Pick a claim id from any existing paper
curl -s "$API_BASE/api/claims/<CLAIM_ID>" | jq .

# Trigger on-demand extraction (first call runs multi-source pipeline +
# Claude; subsequent calls return cached)
curl -s -X POST "$API_BASE/api/claims/<CLAIM_ID>/extract-provenance" \
     -H "Content-Type: application/json" -d '{}' | jq .

# Author drilldown (inline-enriches on first call)
curl -s "$API_BASE/api/authors/profile/by-openalex/A5012345678" | jq .
```

## 7. Cost model

Per-claim cost for a single on-demand extraction:
- 1 Haiku call on aggregator: ~$0.001–$0.005 depending on how much
  full_text is included.
- External API calls (Unpaywall, Semantic Scholar, arXiv) are free.
- CORE API is free under the public tier.

Per-author bio: ~$0.0005–$0.001 (Haiku, ~300 tokens out).

Costs are one-per-entity — cache hits are free.
