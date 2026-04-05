-- Migration 007: Highlights, Learning Paths & Reading Sessions
-- Enables text highlighting, learning paths, and reading behavior tracking

-- User highlights on various content types
CREATE TABLE IF NOT EXISTS highlights (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    source_type TEXT NOT NULL CHECK (source_type IN ('paper_abstract', 'ai_response', 'claim', 'paper_section')),
    source_id UUID NOT NULL,
    highlighted_text TEXT NOT NULL,
    start_offset INT,
    end_offset INT,
    annotation TEXT,
    color TEXT DEFAULT '#E8B931',
    concept_ids UUID[] DEFAULT '{}',
    is_public BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Learning paths — curated sequences of highlights, concepts, papers
CREATE TABLE IF NOT EXISTS learning_paths (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT,
    is_public BOOLEAN DEFAULT false,
    domain TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Items within a learning path
CREATE TABLE IF NOT EXISTS learning_path_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    learning_path_id UUID NOT NULL REFERENCES learning_paths(id) ON DELETE CASCADE,
    item_type TEXT NOT NULL CHECK (item_type IN ('highlight', 'concept', 'paper')),
    item_id UUID NOT NULL,
    position INT NOT NULL DEFAULT 0,
    annotation TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Reading sessions — tracks reading behavior per paper
CREATE TABLE IF NOT EXISTS reading_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    paper_id UUID NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    started_at TIMESTAMPTZ DEFAULT now(),
    ended_at TIMESTAMPTZ,
    total_seconds INT DEFAULT 0,
    sections_visited JSONB DEFAULT '[]'::jsonb,
    scroll_depth FLOAT DEFAULT 0,
    concept_focus JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_highlights_user_id ON highlights(user_id);
CREATE INDEX IF NOT EXISTS idx_highlights_source ON highlights(source_type, source_id);
CREATE INDEX IF NOT EXISTS idx_highlights_public ON highlights(is_public) WHERE is_public = true;
CREATE INDEX IF NOT EXISTS idx_learning_paths_user_id ON learning_paths(user_id);
CREATE INDEX IF NOT EXISTS idx_learning_path_items_path_id ON learning_path_items(learning_path_id);
CREATE INDEX IF NOT EXISTS idx_reading_sessions_user_id ON reading_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_reading_sessions_paper ON reading_sessions(user_id, paper_id);

-- Updated_at triggers
CREATE TRIGGER highlights_updated_at
    BEFORE UPDATE ON highlights
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER learning_paths_updated_at
    BEFORE UPDATE ON learning_paths
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
