-- Migration 010: Community Layer — comments, votes
-- Enables threaded paper comments and voting on content

-- Threaded paper comments
CREATE TABLE IF NOT EXISTS paper_comments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    paper_id UUID NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    parent_id UUID REFERENCES paper_comments(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    upvotes INT DEFAULT 0,
    downvotes INT DEFAULT 0,
    flags INT DEFAULT 0,
    is_hidden BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Community votes (on comments, highlights, learning paths)
CREATE TABLE IF NOT EXISTS community_votes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    target_type TEXT NOT NULL CHECK (target_type IN ('comment', 'highlight', 'learning_path')),
    target_id UUID NOT NULL,
    vote_type TEXT NOT NULL CHECK (vote_type IN ('upvote', 'downvote', 'flag')),
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(user_id, target_type, target_id)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_paper_comments_paper ON paper_comments(paper_id);
CREATE INDEX IF NOT EXISTS idx_paper_comments_parent ON paper_comments(parent_id);
CREATE INDEX IF NOT EXISTS idx_paper_comments_user ON paper_comments(user_id);
CREATE INDEX IF NOT EXISTS idx_paper_comments_hidden ON paper_comments(is_hidden) WHERE is_hidden = false;
CREATE INDEX IF NOT EXISTS idx_community_votes_target ON community_votes(target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_community_votes_user ON community_votes(user_id);

-- Updated_at trigger
CREATE TRIGGER paper_comments_updated_at
    BEFORE UPDATE ON paper_comments
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
