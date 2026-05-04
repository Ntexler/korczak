-- Migration 025: Korczak Consciousness — learning log, reflections, curiosity queue
-- Run in Supabase SQL Editor

-- Learning Log — everything Korczak learns, when, and from whom
CREATE TABLE IF NOT EXISTS learning_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entry_type TEXT NOT NULL CHECK (entry_type IN (
        'discovered',        -- found a new concept or connection
        'confirmed',         -- existing knowledge confirmed by new source
        'contradicted',      -- found evidence contradicting existing knowledge
        'deepened',          -- gained deeper understanding of existing concept
        'connected',         -- found new connection between existing concepts
        'corrected',         -- corrected a misconception
        'from_expert',       -- learned from human expert
        'from_student'       -- learned from a student's question/insight
    )),
    concept_id UUID,
    concept_name TEXT,
    field TEXT,
    summary TEXT NOT NULL,               -- "Learned that X because Y"
    detail TEXT,                          -- fuller explanation
    source TEXT,                          -- where this came from
    source_ref TEXT,                      -- URL, paper DOI, expert name
    confidence FLOAT DEFAULT 0.5,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_learning_log_date ON learning_log (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_learning_log_field ON learning_log (field, created_at DESC);

-- Reflections — Korczak's periodic self-summaries
CREATE TABLE IF NOT EXISTS reflections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reflection_type TEXT NOT NULL CHECK (reflection_type IN ('daily', 'weekly', 'milestone')),
    field TEXT,
    period_start TIMESTAMPTZ,
    period_end TIMESTAMPTZ,
    summary TEXT NOT NULL,                -- "This week I learned 12 new concepts..."
    key_discoveries TEXT[],               -- most important things learned
    open_questions TEXT[],                -- things still unclear
    contradictions_found TEXT[],          -- conflicts discovered
    connections_made INT DEFAULT 0,
    concepts_enriched INT DEFAULT 0,
    sources_consulted INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Curiosity Queue — things Korczak wants to explore next
CREATE TABLE IF NOT EXISTS curiosity_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    question TEXT NOT NULL,
    field TEXT,
    concept_id UUID,
    concept_name TEXT,
    trigger TEXT,                          -- what made Korczak curious
    priority INT DEFAULT 0,
    status TEXT DEFAULT 'curious' CHECK (status IN ('curious', 'exploring', 'answered', 'parked')),
    answer TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_curiosity_status ON curiosity_queue (status, priority DESC);
