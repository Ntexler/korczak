-- Migration 021: Obsidian Vault Integration — vault analyses + attention signals
-- Run in Supabase SQL Editor

-- Vault analysis snapshots — each upload creates an analysis
CREATE TABLE IF NOT EXISTS vault_analyses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    note_count INT DEFAULT 0,
    total_links INT DEFAULT 0,
    total_tags INT DEFAULT 0,
    mapped_concepts INT DEFAULT 0,            -- notes that matched Korczak concepts
    unmapped_notes INT DEFAULT 0,             -- notes with no concept match
    coverage_pct FLOAT DEFAULT 0,             -- % of field concepts user has notes on
    field TEXT,                                -- primary field detected
    raw_stats JSONB DEFAULT '{}'::jsonb,       -- detailed stats (tags freq, link density, etc.)
    status TEXT CHECK (status IN ('processing', 'complete', 'failed')) DEFAULT 'processing',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_vault_analyses_user ON vault_analyses (user_id, created_at DESC);

-- Individual note mappings — each user note mapped to concept(s)
CREATE TABLE IF NOT EXISTS vault_note_mappings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    vault_analysis_id UUID REFERENCES vault_analyses(id) ON DELETE CASCADE,
    user_id UUID NOT NULL,
    note_title TEXT NOT NULL,
    note_tags TEXT[] DEFAULT '{}',
    matched_concept_id UUID,                   -- Korczak concept this note maps to (NULL if unmapped)
    matched_concept_name TEXT,
    match_confidence FLOAT DEFAULT 0,          -- how confident is the mapping (0-1)
    note_excerpt TEXT,                          -- first ~200 chars of note content
    outgoing_links TEXT[] DEFAULT '{}',         -- [[wikilinks]] found in the note
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_vault_mappings_analysis ON vault_note_mappings (vault_analysis_id);
CREATE INDEX IF NOT EXISTS idx_vault_mappings_concept ON vault_note_mappings (matched_concept_id);

-- Attention signals — things Korczak should investigate deeper
CREATE TABLE IF NOT EXISTS attention_signals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    signal_type TEXT CHECK (signal_type IN (
        'vault_note', 'saved_paper', 'rated', 'flagged',
        'gap_detected', 'misconception_detected', 'connection_found'
    )) NOT NULL,
    direction TEXT CHECK (direction IN ('interest', 'skepticism', 'neutral')) DEFAULT 'neutral',
    target_type TEXT CHECK (target_type IN ('concept', 'paper', 'claim', 'note')) NOT NULL,
    target_id TEXT,                             -- concept_id, paper_id, or note title
    target_name TEXT,                           -- human-readable name
    context TEXT,                               -- why this signal was created
    status TEXT CHECK (status IN ('pending', 'processing', 'resolved', 'dismissed')) DEFAULT 'pending',
    resolution JSONB,                           -- what Korczak found when investigating
    created_at TIMESTAMPTZ DEFAULT now(),
    resolved_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_attention_user ON attention_signals (user_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_attention_target ON attention_signals (target_type, target_id);

-- Vault insights — generated findings from vault analysis
CREATE TABLE IF NOT EXISTS vault_insights (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    vault_analysis_id UUID REFERENCES vault_analyses(id) ON DELETE CASCADE,
    user_id UUID NOT NULL,
    insight_type TEXT CHECK (insight_type IN (
        'gap', 'misconception', 'hidden_connection',
        'recommendation', 'strength', 'progress'
    )) NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    severity TEXT CHECK (severity IN ('info', 'suggestion', 'important')) DEFAULT 'suggestion',
    related_concepts TEXT[] DEFAULT '{}',       -- concept names involved
    related_notes TEXT[] DEFAULT '{}',          -- user note titles involved
    action_prompt TEXT,                         -- suggested follow-up question for Korczak
    dismissed BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_vault_insights_user ON vault_insights (user_id, dismissed, created_at DESC);
