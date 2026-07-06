-- Migration 028: Propositions — the atomic unit of real understanding
-- Run in Supabase SQL Editor

-- A proposition is ONE canonical claim that may be asserted/negated/qualified
-- by many papers. "Sleep improves memory consolidation" is one proposition
-- whether it appears in 50 papers in 50 phrasings.
CREATE TABLE IF NOT EXISTS propositions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_text TEXT NOT NULL,
    embedding vector(1536),
    field TEXT,
    -- evidence balance (updated by the proposition engine)
    assert_count INT DEFAULT 0,       -- papers asserting it
    negate_count INT DEFAULT 0,       -- papers asserting the opposite
    qualify_count INT DEFAULT 0,      -- papers asserting "yes, but"
    evidence_mass FLOAT DEFAULT 0,    -- weighted support (citations, quality)
    consensus_status TEXT DEFAULT 'emerging'
        CHECK (consensus_status IN ('consensus', 'emerging', 'contested', 'unverified')),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Which claims (from which papers) map to which proposition, and HOW
CREATE TABLE IF NOT EXISTS claim_propositions (
    claim_id UUID NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    proposition_id UUID NOT NULL REFERENCES propositions(id) ON DELETE CASCADE,
    stance TEXT NOT NULL DEFAULT 'asserts'
        CHECK (stance IN ('asserts', 'negates', 'qualifies')),
    match_confidence FLOAT DEFAULT 0.8,
    PRIMARY KEY (claim_id, proposition_id)
);

CREATE INDEX IF NOT EXISTS idx_claim_props_prop ON claim_propositions (proposition_id);

-- Argument structure between propositions: what rests on what
CREATE TABLE IF NOT EXISTS proposition_edges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id UUID NOT NULL REFERENCES propositions(id) ON DELETE CASCADE,
    target_id UUID NOT NULL REFERENCES propositions(id) ON DELETE CASCADE,
    edge_type TEXT NOT NULL DEFAULT 'PREMISE_OF'
        CHECK (edge_type IN ('PREMISE_OF', 'SUPPORTS', 'CONTRADICTS', 'QUALIFIES')),
    confidence FLOAT DEFAULT 0.5,
    explanation TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(source_id, target_id, edge_type)
);

-- Concept ↔ proposition linkage (which concept a proposition is about)
CREATE TABLE IF NOT EXISTS concept_propositions (
    concept_id UUID NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
    proposition_id UUID NOT NULL REFERENCES propositions(id) ON DELETE CASCADE,
    PRIMARY KEY (concept_id, proposition_id)
);

-- pgvector similarity search for proposition matching
CREATE OR REPLACE FUNCTION match_propositions(
    query_embedding vector(1536),
    match_threshold float DEFAULT 0.85,
    match_count int DEFAULT 5
)
RETURNS TABLE (id uuid, canonical_text text, similarity float)
LANGUAGE sql STABLE AS $$
    SELECT p.id, p.canonical_text,
           1 - (p.embedding <=> query_embedding) AS similarity
    FROM propositions p
    WHERE p.embedding IS NOT NULL
      AND 1 - (p.embedding <=> query_embedding) > match_threshold
    ORDER BY p.embedding <=> query_embedding
    LIMIT match_count;
$$;

-- Atlas support: per-concept field span (border concepts live on the seams)
ALTER TABLE concepts ADD COLUMN IF NOT EXISTS field_span TEXT[] DEFAULT '{}';
CREATE INDEX IF NOT EXISTS idx_concepts_field_span ON concepts USING GIN (field_span);
