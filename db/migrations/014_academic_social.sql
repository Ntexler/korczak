-- =============================================
-- KORCZAK AI — Academic Social Network
-- Migration 014: Researcher profiles, summaries, discussions
-- =============================================

-- Researcher profiles: public identity in the academic community
CREATE TABLE researcher_profiles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
  display_name TEXT NOT NULL,
  bio TEXT,
  institution TEXT,
  role TEXT,
  -- 'student', 'researcher', 'professor', 'independent'
  research_interests TEXT[] DEFAULT '{}',
  website_url TEXT,
  orcid TEXT,
  is_public BOOLEAN DEFAULT true,
  reputation_score INT DEFAULT 0,
  -- Earned from contributions
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),

  UNIQUE(user_id)
);

-- Follows: researcher follows researcher
CREATE TABLE researcher_follows (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  follower_id UUID NOT NULL REFERENCES researcher_profiles(id) ON DELETE CASCADE,
  following_id UUID NOT NULL REFERENCES researcher_profiles(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ DEFAULT now(),

  UNIQUE(follower_id, following_id),
  CHECK(follower_id != following_id)
);

-- Community summaries: user-written interpretations on concepts
CREATE TABLE concept_summaries (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  concept_id UUID NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
  author_id UUID NOT NULL REFERENCES researcher_profiles(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  -- Markdown supported
  version INT DEFAULT 1,
  referenced_concepts UUID[] DEFAULT '{}',
  -- Cross-links to other concepts
  upvotes INT DEFAULT 0,
  downvotes INT DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Summary edit history: every version preserved
CREATE TABLE summary_versions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  summary_id UUID NOT NULL REFERENCES concept_summaries(id) ON DELETE CASCADE,
  version INT NOT NULL,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  edited_at TIMESTAMPTZ DEFAULT now(),
  edit_reason TEXT
);

-- Summary votes (separate from upvote counter for user tracking)
CREATE TABLE summary_votes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  summary_id UUID NOT NULL REFERENCES concept_summaries(id) ON DELETE CASCADE,
  voter_id UUID NOT NULL REFERENCES researcher_profiles(id) ON DELETE CASCADE,
  vote_type TEXT NOT NULL CHECK (vote_type IN ('up', 'down')),
  created_at TIMESTAMPTZ DEFAULT now(),

  UNIQUE(summary_id, voter_id)
);

-- Discussion threads: attached to any node, edge, or claim
CREATE TABLE discussions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  -- Polymorphic target: what this discussion is about
  target_type TEXT NOT NULL
    CHECK (target_type IN ('concept', 'relationship', 'claim', 'summary', 'paper')),
  target_id UUID NOT NULL,
  author_id UUID NOT NULL REFERENCES researcher_profiles(id) ON DELETE CASCADE,
  title TEXT,
  body TEXT NOT NULL,
  parent_id UUID REFERENCES discussions(id) ON DELETE CASCADE,
  -- For threaded replies
  upvotes INT DEFAULT 0,
  downvotes INT DEFAULT 0,
  is_resolved BOOLEAN DEFAULT false,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Discussion votes
CREATE TABLE discussion_votes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  discussion_id UUID NOT NULL REFERENCES discussions(id) ON DELETE CASCADE,
  voter_id UUID NOT NULL REFERENCES researcher_profiles(id) ON DELETE CASCADE,
  vote_type TEXT NOT NULL CHECK (vote_type IN ('up', 'down')),
  created_at TIMESTAMPTZ DEFAULT now(),

  UNIQUE(discussion_id, voter_id)
);

-- Activity feed: track actions for followers
CREATE TABLE activity_feed (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  researcher_id UUID NOT NULL REFERENCES researcher_profiles(id) ON DELETE CASCADE,
  action_type TEXT NOT NULL
    CHECK (action_type IN (
      'wrote_summary', 'edited_summary', 'started_discussion',
      'replied_discussion', 'proposed_connection', 'voted',
      'followed_researcher', 'translated_paper'
    )),
  target_type TEXT,
  target_id UUID,
  metadata JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes
CREATE INDEX idx_researcher_profiles_user ON researcher_profiles(user_id);
CREATE INDEX idx_researcher_follows_follower ON researcher_follows(follower_id);
CREATE INDEX idx_researcher_follows_following ON researcher_follows(following_id);
CREATE INDEX idx_concept_summaries_concept ON concept_summaries(concept_id);
CREATE INDEX idx_concept_summaries_author ON concept_summaries(author_id);
CREATE INDEX idx_discussions_target ON discussions(target_type, target_id);
CREATE INDEX idx_discussions_parent ON discussions(parent_id);
CREATE INDEX idx_activity_feed_researcher ON activity_feed(researcher_id);
CREATE INDEX idx_activity_feed_created ON activity_feed(created_at DESC);
