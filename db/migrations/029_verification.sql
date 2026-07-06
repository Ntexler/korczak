-- Migration 029: Verification Court — truth checks before knowledge enters
-- Run in Supabase SQL Editor

-- Full verification record attached to every enrichment:
-- {grounding: {passed, quote, matched}, corroboration: {independent_supports,
--  contradicts, sources}, refutation: {survived, objections}, verdict, checked_at}
ALTER TABLE pending_enrichments ADD COLUMN IF NOT EXISTS verification JSONB DEFAULT NULL;

-- 'auto_approved' and 'auto_rejected' need to be valid statuses.
-- The original CHECK allowed: pending/approved/rejected/auto_applied.
ALTER TABLE pending_enrichments DROP CONSTRAINT IF EXISTS pending_enrichments_status_check;
ALTER TABLE pending_enrichments ADD CONSTRAINT pending_enrichments_status_check
    CHECK (status IN ('pending', 'approved', 'rejected', 'auto_applied', 'auto_rejected'));

CREATE INDEX IF NOT EXISTS idx_pending_enrichments_auto
    ON pending_enrichments (status, created_at DESC)
    WHERE status IN ('auto_applied', 'auto_rejected');
