-- Migration 025: Learner State Model + Discovery Engine
--
-- Part 1: Learner state — metacognition ("you are here" map)
-- Part 2: Discoveries — autonomous connection finding ("mega brain")

-- =====================================================================
-- Part 1: LEARNER STATE
-- =====================================================================

-- Per-concept mastery per user
CREATE TABLE IF NOT EXISTS user_concept_mastery (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    concept_id UUID NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
    mastery_score FLOAT NOT NULL DEFAULT 0.0 CHECK (mastery_score BETWEEN 0 AND 1),
    mastery_level TEXT NOT NULL DEFAULT 'unseen'
        CHECK (mastery_level IN ('unseen', 'exposed', 'practicing', 'mastered')),
    times_seen INT NOT NULL DEFAULT 0,
    times_assessed INT NOT NULL DEFAULT 0,
    times_correct INT NOT NULL DEFAULT 0,
    last_seen TIMESTAMPTZ,
    last_assessed TIMESTAMPTZ,
    next_review_due TIMESTAMPTZ,  -- spaced repetition (FSRS)
    sr_ease FLOAT DEFAULT 2.5,
    sr_interval INT DEFAULT 1,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, concept_id)
);

CREATE INDEX IF NOT EXISTS ucm_user_idx ON user_concept_mastery(user_id);
CREATE INDEX IF NOT EXISTS ucm_user_level_idx ON user_concept_mastery(user_id, mastery_level);
CREATE INDEX IF NOT EXISTS ucm_review_due_idx ON user_concept_mastery(user_id, next_review_due) WHERE next_review_due IS NOT NULL;

-- Learning paths — structured journeys (user-defined or AI-generated)
CREATE TABLE IF NOT EXISTS learning_paths (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    goal_concept_ids UUID[] NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'paused', 'completed', 'abandoned')),
    generated_by TEXT DEFAULT 'user',  -- 'user' | 'korczak' | 'teacher'
    progress_percent FLOAT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS lp_user_status_idx ON learning_paths(user_id, status);

-- Ordered steps in a learning path
CREATE TABLE IF NOT EXISTS learning_path_steps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    path_id UUID NOT NULL REFERENCES learning_paths(id) ON DELETE CASCADE,
    concept_id UUID NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
    paper_id UUID REFERENCES papers(id),  -- optional: specific paper to read for this step
    position INT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'current', 'done', 'skipped')),
    instruction TEXT,  -- what the learner should do at this step
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS lps_path_pos_idx ON learning_path_steps(path_id, position);

-- User interactions — persistent memory of what a user did
CREATE TABLE IF NOT EXISTS user_interactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    interaction_type TEXT NOT NULL
        CHECK (interaction_type IN (
            'view_paper', 'view_concept', 'complete_assessment',
            'answer_correct', 'answer_incorrect', 'explain_back',
            'ask_question', 'mark_mastered', 'request_simpler',
            'bookmark', 'annotate'
        )),
    paper_id UUID REFERENCES papers(id),
    concept_id UUID REFERENCES concepts(id),
    metadata JSONB DEFAULT '{}',  -- { answer_text, time_spent, etc }
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ui_user_time_idx ON user_interactions(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ui_user_concept_idx ON user_interactions(user_id, concept_id) WHERE concept_id IS NOT NULL;

-- =====================================================================
-- Part 2: DISCOVERIES — Korczak's autonomous findings
-- =====================================================================

-- Things Korczak figured out by analyzing its own graph
CREATE TABLE IF NOT EXISTS discoveries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kind TEXT NOT NULL CHECK (kind IN (
        'analogical_bridge',      -- same concept in different fields
        'citation_gap',           -- two papers that should cite each other
        'contradiction',          -- opposing claims about same thing
        'unrealized_potential',   -- concept with many inputs, no outputs
        'temporal_gap',           -- old testable claim, no new test found
        'cross_lingual_bridge',   -- foreign concept missing from English graph
        'research_direction',     -- a hypothesis Korczak generated
        'orphan_concept'          -- concept with no meaningful connections
    )),
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    claude_reasoning TEXT,

    -- Entities involved
    paper_ids UUID[] DEFAULT '{}',
    concept_ids UUID[] DEFAULT '{}',
    claim_ids UUID[] DEFAULT '{}',

    -- Scores
    confidence FLOAT DEFAULT 0.5 CHECK (confidence BETWEEN 0 AND 1),
    novelty FLOAT DEFAULT 0.5 CHECK (novelty BETWEEN 0 AND 1),  -- surprise value
    importance FLOAT DEFAULT 0.5 CHECK (importance BETWEEN 0 AND 1),

    -- Human review
    reviewed BOOLEAN DEFAULT FALSE,
    review_verdict TEXT CHECK (review_verdict IN ('confirmed', 'rejected', 'needs_evidence', 'partially_correct')),
    review_notes TEXT,
    reviewed_by UUID,
    reviewed_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS disc_kind_idx ON discoveries(kind);
CREATE INDEX IF NOT EXISTS disc_importance_idx ON discoveries(importance DESC, novelty DESC) WHERE NOT reviewed;
CREATE INDEX IF NOT EXISTS disc_reviewed_idx ON discoveries(reviewed);

-- Research hypotheses — more structured form of research_direction discoveries
CREATE TABLE IF NOT EXISTS research_hypotheses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    discovery_id UUID REFERENCES discoveries(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    hypothesis TEXT NOT NULL,
    rationale TEXT,
    predicted_outcome TEXT,
    testable BOOLEAN DEFAULT TRUE,
    method_suggestion TEXT,
    related_concept_ids UUID[] DEFAULT '{}',
    related_paper_ids UUID[] DEFAULT '{}',
    status TEXT DEFAULT 'open'
        CHECK (status IN ('open', 'being_investigated', 'supported', 'refuted', 'abandoned')),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- A simple log of what Korczak scanned
CREATE TABLE IF NOT EXISTS discovery_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_type TEXT NOT NULL,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    discoveries_found INT DEFAULT 0,
    cost_usd FLOAT DEFAULT 0,
    notes TEXT
);
