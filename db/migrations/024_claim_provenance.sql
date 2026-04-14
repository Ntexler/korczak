-- Migration 024: Claim Provenance
-- Supports Feature 6.5 (Article-Grounded Claims).
--
-- Adds provenance columns to `claims` so every claim can surface:
--   - a verbatim quote from the paper that supports it
--   - the quote's approximate location (section / paragraph / page)
--   - a claim category (main / supporting / background / limitation)
--   - examples cited by the author
--   - a record of which external sources were checked during on-demand extraction
--
-- Filling these columns happens two ways:
--   1. During seeding, when full_text is fetched, the updated analysis prompt
--      extracts quote + examples + category directly.
--   2. On demand, via POST /api/claims/{id}/extract-provenance, which runs
--      multiple sources (full_text, Semantic Scholar, CORE, arXiv, Unpaywall)
--      in parallel and aggregates results.

ALTER TABLE claims ADD COLUMN IF NOT EXISTS verbatim_quote TEXT;
COMMENT ON COLUMN claims.verbatim_quote IS 'Direct passage from the source paper that supports this claim (max ~300 chars).';

ALTER TABLE claims ADD COLUMN IF NOT EXISTS quote_location TEXT;
COMMENT ON COLUMN claims.quote_location IS 'Where in the paper the quote appears — e.g., "section 3.2", "Results, para 2", "page 5".';

ALTER TABLE claims ADD COLUMN IF NOT EXISTS claim_category TEXT
  CHECK (claim_category IS NULL OR claim_category IN ('main', 'supporting', 'background', 'limitation'));
COMMENT ON COLUMN claims.claim_category IS 'main = primary finding; supporting = secondary evidence; background = literature review; limitation = acknowledged caveat.';

ALTER TABLE claims ADD COLUMN IF NOT EXISTS examples JSONB DEFAULT '[]'::jsonb;
COMMENT ON COLUMN claims.examples IS 'Examples/cases the author uses to illustrate this claim. Shape: [{ text, kind: "case"|"dataset"|"figure"|"table", location }].';

ALTER TABLE claims ADD COLUMN IF NOT EXISTS provenance_sources JSONB DEFAULT '[]'::jsonb;
COMMENT ON COLUMN claims.provenance_sources IS 'Record of every external source checked during extraction. Shape: [{ source, status: "hit"|"miss"|"error", quote, location, url }].';

ALTER TABLE claims ADD COLUMN IF NOT EXISTS provenance_extracted_at TIMESTAMPTZ;
COMMENT ON COLUMN claims.provenance_extracted_at IS 'Timestamp of last provenance extraction run. NULL = never extracted; cache miss on the extract endpoint.';

-- Partial index so "claims pending extraction" queries are fast
CREATE INDEX IF NOT EXISTS idx_claims_provenance_pending
  ON claims(id)
  WHERE provenance_extracted_at IS NULL;

-- Index on category for lesson builders that fetch "main claims only"
CREATE INDEX IF NOT EXISTS idx_claims_category ON claims(claim_category)
  WHERE claim_category IS NOT NULL;
