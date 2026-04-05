-- =============================================
-- KORCZAK AI — Connection Feedback
-- Migration 012: User feedback on knowledge graph connections
-- =============================================

-- Connection feedback: agree/disagree/suggest on relationship edges
CREATE TABLE connection_feedback (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  relationship_id UUID NOT NULL REFERENCES relationships(id) ON DELETE CASCADE,
  user_id UUID REFERENCES user_profiles(id) ON DELETE SET NULL,
  feedback_type TEXT NOT NULL
    CHECK (feedback_type IN ('agree', 'disagree', 'suggest_alternative', 'report_missing')),
  comment TEXT,
  suggested_connection JSONB,
  -- For 'suggest_alternative': {source_concept_id, target_concept_id, relationship_type, explanation}
  created_at TIMESTAMPTZ DEFAULT now(),

  -- One feedback per user per relationship per type
  UNIQUE(relationship_id, user_id, feedback_type)
);

-- Proposed connections: users suggest missing edges
CREATE TABLE proposed_connections (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES user_profiles(id) ON DELETE SET NULL,
  source_concept_id UUID NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
  target_concept_id UUID NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
  relationship_type TEXT NOT NULL
    CHECK (relationship_type IN (
      'BUILDS_ON', 'CONTRADICTS', 'EXTENDS', 'APPLIES',
      'ANALOGOUS_TO', 'PART_OF', 'PREREQUISITE_FOR',
      'RESPONDS_TO', 'INTRODUCES', 'SUPPORTS', 'WEAKENS'
    )),
  explanation TEXT NOT NULL,
  status TEXT DEFAULT 'pending'
    CHECK (status IN ('pending', 'accepted', 'rejected')),
  upvotes INT DEFAULT 0,
  downvotes INT DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT now(),
  reviewed_at TIMESTAMPTZ
);

-- Indexes
CREATE INDEX idx_connection_feedback_rel ON connection_feedback(relationship_id);
CREATE INDEX idx_connection_feedback_user ON connection_feedback(user_id);
CREATE INDEX idx_proposed_connections_status ON proposed_connections(status);
CREATE INDEX idx_proposed_connections_concepts ON proposed_connections(source_concept_id, target_concept_id);
