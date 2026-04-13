-- Migration 020: Briefings — cached personalized briefings
-- Run in Supabase SQL Editor

CREATE TABLE IF NOT EXISTS briefings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    briefing_type TEXT CHECK (briefing_type IN ('daily', 'weekly', 'deep_dive')) NOT NULL,
    content TEXT NOT NULL,
    raw_data JSONB DEFAULT '{}'::jsonb,
    tokens_used INT DEFAULT 0,
    read_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_briefings_user ON briefings (user_id, created_at DESC);

-- Briefing preferences per user
CREATE TABLE IF NOT EXISTS briefing_preferences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL UNIQUE,
    enabled BOOLEAN DEFAULT true,
    frequency TEXT CHECK (frequency IN ('daily', 'weekly', 'none')) DEFAULT 'weekly',
    preferred_time TEXT DEFAULT '09:00',
    topics_filter TEXT[] DEFAULT '{}',
    locale TEXT DEFAULT 'en',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
