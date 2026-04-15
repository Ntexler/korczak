-- Migration 025: Paper Access Fields
-- Supports Feature 6.5 (Article-Grounded Claims).
--
-- Adds a user-facing access URL and a structured access-status indicator to
-- `papers`, so the UI can show "Open access — read on Unpaywall" / "Paywalled
-- at publisher, preprint available on arXiv" / "Author manuscript on ResearchGate".
--
-- Backfill is handled by a separate script (backend/pipeline/backfill_paper_access.py)
-- that re-runs Unpaywall + OpenAlex lookups for existing papers.

ALTER TABLE papers ADD COLUMN IF NOT EXISTS access_url TEXT;
COMMENT ON COLUMN papers.access_url IS 'Best available reading URL — Unpaywall OA link, preprint, or DOI URL as fallback.';

ALTER TABLE papers ADD COLUMN IF NOT EXISTS access_status TEXT
  CHECK (access_status IS NULL OR access_status IN (
    'open',          -- freely readable (gold OA, green OA, etc.)
    'paywalled',     -- publisher paywall, no known alt
    'hybrid',        -- publisher paywall but OA version available elsewhere
    'preprint',      -- only preprint version is freely readable
    'author_copy',   -- author-uploaded copy available (ResearchGate, personal site)
    'unknown'        -- not yet resolved
  ));
COMMENT ON COLUMN papers.access_status IS 'Structured access indicator for UI: open, paywalled, hybrid, preprint, author_copy, unknown.';

ALTER TABLE papers ADD COLUMN IF NOT EXISTS access_resolved_at TIMESTAMPTZ;
COMMENT ON COLUMN papers.access_resolved_at IS 'When access_url/access_status was last resolved. Used to decide whether to re-check a paywalled paper for later OA release.';

-- Index for "find papers we have not yet resolved access for" backfill pass
CREATE INDEX IF NOT EXISTS idx_papers_access_unresolved
  ON papers(id)
  WHERE access_status IS NULL OR access_status = 'unknown';
