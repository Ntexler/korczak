-- Migration 006: Paper Library + Reading Lists
-- Enables users to save papers, organize into lists, and get smart recommendations

-- User's saved papers
CREATE TABLE IF NOT EXISTS user_papers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    paper_id UUID NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'unread' CHECK (status IN ('unread', 'reading', 'completed', 'archived')),
    notes TEXT,
    rating SMALLINT CHECK (rating IS NULL OR (rating >= 1 AND rating <= 5)),
    tags JSONB DEFAULT '[]'::jsonb,
    save_context TEXT DEFAULT 'browsing' CHECK (save_context IN ('search_result', 'recommendation', 'chat_reference', 'syllabus', 'browsing')),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(user_id, paper_id)
);

-- Reading lists (manual or syllabus-imported)
CREATE TABLE IF NOT EXISTS reading_lists (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT,
    is_public BOOLEAN DEFAULT false,
    color TEXT DEFAULT '#E8B931',
    source_type TEXT DEFAULT 'manual' CHECK (source_type IN ('manual', 'syllabus', 'mit_ocw', 'auto_generated')),
    source_url TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Ordered junction: papers in reading lists
CREATE TABLE IF NOT EXISTS reading_list_papers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reading_list_id UUID NOT NULL REFERENCES reading_lists(id) ON DELETE CASCADE,
    paper_id UUID NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    position INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(reading_list_id, paper_id)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_user_papers_user_id ON user_papers(user_id);
CREATE INDEX IF NOT EXISTS idx_user_papers_status ON user_papers(user_id, status);
CREATE INDEX IF NOT EXISTS idx_user_papers_save_context ON user_papers(user_id, save_context);
CREATE INDEX IF NOT EXISTS idx_reading_lists_user_id ON reading_lists(user_id);
CREATE INDEX IF NOT EXISTS idx_reading_list_papers_list_id ON reading_list_papers(reading_list_id);
CREATE INDEX IF NOT EXISTS idx_reading_list_papers_position ON reading_list_papers(reading_list_id, position);

-- Updated_at trigger
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER user_papers_updated_at
    BEFORE UPDATE ON user_papers
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER reading_lists_updated_at
    BEFORE UPDATE ON reading_lists
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
