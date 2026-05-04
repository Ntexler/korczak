-- Migration 024: Expert connector — professors and domain experts
-- Run in Supabase SQL Editor

CREATE TABLE IF NOT EXISTS experts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    field TEXT NOT NULL,
    institution TEXT,
    specialization TEXT,
    contact_type TEXT NOT NULL CHECK (contact_type IN ('whatsapp', 'email', 'telegram', 'manual')),
    contact_id TEXT NOT NULL,
    status TEXT DEFAULT 'active' CHECK (status IN ('active', 'paused', 'inactive')),
    questions_sent INT DEFAULT 0,
    responses_received INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS expert_conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    expert_id UUID REFERENCES experts(id) ON DELETE CASCADE,
    concept_id UUID,
    concept_name TEXT,
    question TEXT NOT NULL,
    response TEXT,
    status TEXT DEFAULT 'sent' CHECK (status IN ('sent', 'responded', 'expired')),
    responded_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_expert_conv_expert ON expert_conversations (expert_id, created_at DESC);

-- Manual source submissions (admin adds URLs for agent to process)
CREATE TABLE IF NOT EXISTS manual_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    url TEXT NOT NULL,
    field TEXT,
    source_type TEXT DEFAULT 'url' CHECK (source_type IN ('url', 'pdf', 'text', 'reddit', 'forum')),
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'processed', 'failed')),
    notes TEXT,
    submitted_by TEXT DEFAULT 'admin',
    result JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);
