-- Migration 033: The echo layer — a moment's textual wake.
-- Significant footage leaves ripples: news volume, TV replays, Wikipedia
-- attention spikes, search surges. We read the ripples to find WHICH moment
-- mattered and WHEN — cheaply, from the collective human response — before
-- ever paying for frame-level visual analysis.
-- Run in Supabase SQL Editor.

CREATE TABLE IF NOT EXISTS concept_echoes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    concept_id UUID REFERENCES concepts(id) ON DELETE CASCADE,

    kind TEXT NOT NULL CHECK (kind IN (
        'news_volume',      -- GDELT: coverage volume over time
        'tv_replay',        -- GDELT TV: airtime a moment got on TV news
        'attention_spike',  -- Wikipedia: daily pageview surge
        'rising_query',     -- Google Trends: what people suddenly searched
        'analysis'          -- an op-ed / analysis article (human interpretation)
    )),
    source TEXT,                      -- gdelt | wikipedia | google_trends
    moment_date DATE,                 -- when the wake peaked
    signal_strength REAL DEFAULT 0,   -- 0..1 normalized within the scan

    -- The human interpretation the culture gave the moment (Layer-1 material)
    headline TEXT,
    url TEXT,
    excerpt TEXT,
    term TEXT,                        -- for rising_query: the surged search term

    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_concept_echoes_concept ON concept_echoes (concept_id);
CREATE INDEX IF NOT EXISTS idx_concept_echoes_date ON concept_echoes (moment_date);
CREATE INDEX IF NOT EXISTS idx_concept_echoes_kind ON concept_echoes (kind);
