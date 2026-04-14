-- Migration 023: Canonical works tracking
-- Mark foundational/canonical papers for each field so they get recommended first
-- regardless of citation count. Also allows "stub" entries for canonical works
-- we know about but haven't been able to seed from OpenAlex yet.

ALTER TABLE papers
    ADD COLUMN IF NOT EXISTS canonical BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS canonical_field TEXT,
    ADD COLUMN IF NOT EXISTS canonical_rank INTEGER,  -- 1 = most canonical (Origin of Species), higher = less canonical
    ADD COLUMN IF NOT EXISTS canonical_reason TEXT,   -- why this is canonical
    ADD COLUMN IF NOT EXISTS is_stub BOOLEAN DEFAULT FALSE;  -- true if we only have metadata, no OpenAlex/analysis yet

CREATE INDEX IF NOT EXISTS papers_canonical_idx ON papers(canonical) WHERE canonical = TRUE;
CREATE INDEX IF NOT EXISTS papers_canonical_field_idx ON papers(canonical_field, canonical_rank) WHERE canonical = TRUE;

-- Canonical works table: curated list of works that *should* be in the graph for each field
-- Used to create stubs and to track completion
CREATE TABLE IF NOT EXISTS canonical_works (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    field TEXT NOT NULL,
    title TEXT NOT NULL,
    author TEXT,
    year INTEGER,
    why TEXT,  -- why this work is canonical
    rank INTEGER,  -- ordering within field
    paper_id UUID REFERENCES papers(id) ON DELETE SET NULL,  -- linked when seeded
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(field, title)
);

CREATE INDEX IF NOT EXISTS canonical_works_field_idx ON canonical_works(field, rank);
CREATE INDEX IF NOT EXISTS canonical_works_paper_idx ON canonical_works(paper_id);
