-- Migration 016: Add full_text columns to papers table
-- Supports storing full paper text fetched from open-access sources

ALTER TABLE papers ADD COLUMN IF NOT EXISTS full_text TEXT;
ALTER TABLE papers ADD COLUMN IF NOT EXISTS full_text_source TEXT;

COMMENT ON COLUMN papers.full_text IS 'Full text of the paper, fetched from open-access sources';
COMMENT ON COLUMN papers.full_text_source IS 'Source of the full text: unpaywall, semantic_scholar, etc.';
