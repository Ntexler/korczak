-- Migration 022: Production infrastructure — rate limiting, embedding cache, job queue
-- Run in Supabase SQL Editor

-- Embedding cache — avoid recalculating embeddings
CREATE TABLE IF NOT EXISTS embedding_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    text_hash TEXT NOT NULL UNIQUE,           -- SHA256 of input text
    model TEXT NOT NULL DEFAULT 'text-embedding-3-small',
    embedding vector(1536),
    token_count INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_embedding_cache_hash ON embedding_cache (text_hash);

-- Rate limit tracking per user
CREATE TABLE IF NOT EXISTS rate_limits (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    endpoint TEXT NOT NULL,                   -- e.g. "chat", "search", "export"
    window_start TIMESTAMPTZ NOT NULL,
    request_count INT DEFAULT 1,
    UNIQUE(user_id, endpoint, window_start)
);

CREATE INDEX IF NOT EXISTS idx_rate_limits_user ON rate_limits (user_id, endpoint, window_start DESC);

-- Background job queue
CREATE TABLE IF NOT EXISTS job_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_type TEXT NOT NULL CHECK (job_type IN (
        'seed_papers', 'analyze_paper', 'generate_embeddings',
        'vault_analysis', 'briefing_generation', 'syllabus_scrape'
    )),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN (
        'pending', 'processing', 'completed', 'failed', 'cancelled'
    )),
    payload JSONB DEFAULT '{}'::jsonb,
    result JSONB,
    error TEXT,
    priority INT DEFAULT 0,                   -- higher = process first
    user_id TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_job_queue_status ON job_queue (status, priority DESC, created_at);

-- Add teaching_preferences column to user_profiles (for pedagogy engine)
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS teaching_preferences JSONB DEFAULT '{}'::jsonb;

-- API usage tracking (for billing / monitoring)
CREATE TABLE IF NOT EXISTS api_usage (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    model TEXT,                                -- Claude model used
    input_tokens INT DEFAULT 0,
    output_tokens INT DEFAULT 0,
    cost_usd FLOAT DEFAULT 0,
    response_ms INT DEFAULT 0,                -- response time
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_api_usage_user ON api_usage (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_api_usage_daily ON api_usage (created_at);
