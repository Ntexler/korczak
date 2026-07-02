-- Migration 026: Consensus tiers — only agreed knowledge is Korczak's base
-- Run in Supabase SQL Editor

-- Knowledge tier on concepts:
--   consensus   = multiple independent ACADEMIC sources agree, no contradictions
--   emerging    = academically sourced but few sources yet
--   contested   = academic sources actively disagree
--   unverified  = only non-academic backing (e.g. Wikipedia-only definition)
ALTER TABLE concepts ADD COLUMN IF NOT EXISTS consensus_status TEXT
    DEFAULT 'emerging'
    CHECK (consensus_status IN ('consensus', 'emerging', 'contested', 'unverified'));

ALTER TABLE concepts ADD COLUMN IF NOT EXISTS consensus_score FLOAT DEFAULT 0
    CHECK (consensus_score BETWEEN 0 AND 1);

-- Where the definition came from — academic base vs external validation
-- 'paper_analysis' | 'openalex' | 'claude_generated' | 'wikipedia' | 'expert'
ALTER TABLE concepts ADD COLUMN IF NOT EXISTS definition_source TEXT DEFAULT 'paper_analysis';

-- Wikipedia/Wikidata can VALIDATE but never BE the base
ALTER TABLE concepts ADD COLUMN IF NOT EXISTS external_validation JSONB DEFAULT '{}'::jsonb;
-- e.g. {"wikipedia": {"matches": true, "url": "...", "checked_at": "..."}}

-- Same tiers on claims
ALTER TABLE claims ADD COLUMN IF NOT EXISTS consensus_status TEXT
    DEFAULT 'emerging'
    CHECK (consensus_status IN ('consensus', 'emerging', 'contested', 'unverified'));

CREATE INDEX IF NOT EXISTS idx_concepts_consensus ON concepts (consensus_status);
CREATE INDEX IF NOT EXISTS idx_claims_consensus ON claims (consensus_status);

-- Chappie's deep-dive journeys — full record of every learning walk
CREATE TABLE IF NOT EXISTS chappie_journeys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    field TEXT,
    start_concept TEXT,                       -- where the walk began
    path JSONB DEFAULT '[]'::jsonb,           -- [{paper, via, hop}] citation trail
    sources_consulted JSONB DEFAULT '[]'::jsonb,  -- [{source, query, result_summary}]
    synthesis TEXT,                            -- what Chappie now understands
    consensus_found TEXT[],                    -- points of agreement discovered
    contested_found TEXT[],                    -- disagreements discovered
    open_questions TEXT[],                     -- what remains unclear
    hops INT DEFAULT 0,
    papers_read INT DEFAULT 0,
    status TEXT DEFAULT 'walking' CHECK (status IN ('walking', 'complete', 'aborted')),
    created_at TIMESTAMPTZ DEFAULT now(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_journeys_field ON chappie_journeys (field, created_at DESC);
