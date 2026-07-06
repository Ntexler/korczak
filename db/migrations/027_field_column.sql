-- Migration 027: persisted field column — kills the "fetch ALL papers" pattern
-- Run in Supabase SQL Editor

-- The audit found 7 call sites that fetch the ENTIRE papers table on every
-- request just to re-run a 120-entry substring map in Python. Persist the
-- normalized field once, at write time, and index it.
ALTER TABLE papers ADD COLUMN IF NOT EXISTS field TEXT;
CREATE INDEX IF NOT EXISTS idx_papers_field ON papers (field);

-- Rejection memory: sources that keep getting rejected lose credibility,
-- and rejected proposals are not re-proposed
CREATE INDEX IF NOT EXISTS idx_pending_enrichments_concept_status
    ON pending_enrichments (concept_id, enrichment_type, status);
