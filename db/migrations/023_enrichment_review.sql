-- Migration 023: Enrichment review queue — admin approval for auto-discovered knowledge
-- Run in Supabase SQL Editor

CREATE TABLE IF NOT EXISTS pending_enrichments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    concept_id UUID REFERENCES concepts(id) ON DELETE CASCADE,
    concept_name TEXT NOT NULL,
    field TEXT,
    enrichment_type TEXT NOT NULL CHECK (enrichment_type IN (
        'definition', 'claim', 'connection', 'source', 'confidence_update'
    )),
    source TEXT NOT NULL,                      -- 'scibot', 'multi_search', 'learning_agent'
    content TEXT NOT NULL,                     -- the proposed enrichment content
    references JSONB DEFAULT '[]'::jsonb,      -- supporting references
    question_asked TEXT,                       -- what question led to this
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN (
        'pending', 'approved', 'rejected', 'auto_applied'
    )),
    reviewed_by TEXT,                          -- admin user_id who approved/rejected
    review_note TEXT,                          -- reason for approval/rejection
    priority INT DEFAULT 0,                   -- higher = more important
    created_at TIMESTAMPTZ DEFAULT now(),
    reviewed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_pending_enrichments_status
    ON pending_enrichments (status, priority DESC, created_at);
CREATE INDEX IF NOT EXISTS idx_pending_enrichments_field
    ON pending_enrichments (field, status);
