-- Migration 032: Media as evidence — video/image/audio that reinforces a claim,
-- interpreted (not just embedded) and audited through the same verification court.
-- Run in Supabase SQL Editor.
--
-- The vision: learning about 9/11 → Korczak shows a founding Bush interview,
-- EMBEDDED in the interface, with its *meaning for the claim* — not a link out.
-- Layered so we can grow from transcript → pragmatic subtext → prosody → visual.

CREATE TABLE IF NOT EXISTS media_evidence (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- What it reinforces
    concept_id UUID REFERENCES concepts(id) ON DELETE CASCADE,
    claim_id UUID,                         -- optional: a specific proposition/claim
    relevance REAL DEFAULT 0.6,

    -- The media itself
    source TEXT NOT NULL,                  -- internet_archive | wikimedia | youtube
    external_id TEXT NOT NULL,             -- IA identifier / YouTube video id / Commons file
    media_kind TEXT DEFAULT 'video' CHECK (media_kind IN ('video', 'image', 'audio')),
    title TEXT,
    embed_url TEXT,                        -- iframe src (yt/archive) or image src (wikimedia)
    page_url TEXT,                         -- source page, for attribution
    thumbnail_url TEXT,
    duration_seconds INT,

    -- Layer 0 — the פשט (grounded fact: this text was actually spoken)
    transcript_excerpt TEXT,
    grounding_quote TEXT,                  -- exact span the interpretation rests on

    -- Layer 1 — meaning for the claim (Korczak's reading; contestable)
    interpretation TEXT,

    -- "Between the lines" — pragmatic subtext (irony, aggression, what's NOT said).
    -- ALWAYS an interpretation, never asserted as the speaker's true intent.
    subtext TEXT,
    subtext_basis TEXT,                    -- the concrete cue it rests on (humility rule)

    -- Layers 2-3 reserved: prosody (audio) + visual/body-language (frames+vision).
    -- {prosody: {...}, visual: {...}} — filled only when we build those passes.
    paralinguistic JSONB DEFAULT '{}'::jsonb,

    -- Audit — same court as everything else. Interpretations are contestable by default.
    consensus_status TEXT DEFAULT 'unverified'
        CHECK (consensus_status IN ('grounded', 'unverified', 'contested', 'refuted')),
    verification JSONB DEFAULT '{}'::jsonb,

    -- Provenance — the platform grows through lecturers/researchers who contribute clips
    contributed_by UUID,                   -- null = Korczak/Chappie brought it
    brought_by TEXT DEFAULT 'chappie',     -- 'chappie' | 'on_demand' | 'contributor'

    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (concept_id, source, external_id)
);

CREATE INDEX IF NOT EXISTS idx_media_evidence_concept ON media_evidence (concept_id);
CREATE INDEX IF NOT EXISTS idx_media_evidence_source ON media_evidence (source);
CREATE INDEX IF NOT EXISTS idx_media_evidence_status ON media_evidence (consensus_status);
