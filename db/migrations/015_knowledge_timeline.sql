-- =============================================
-- KORCZAK AI — Knowledge Timeline
-- Migration 015: Track knowledge evolution over time
-- =============================================

-- Concept history: snapshots of how a concept's understanding changed
CREATE TABLE concept_history (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  concept_id UUID NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
  -- Snapshot of the concept at this point in time
  definition_snapshot TEXT,
  confidence_snapshot FLOAT,
  paper_count_snapshot INT,
  trend_snapshot TEXT,
  -- What triggered this snapshot
  trigger_type TEXT NOT NULL
    CHECK (trigger_type IN ('created', 'definition_changed', 'confidence_changed',
                            'trend_changed', 'major_paper', 'community_edit')),
  trigger_source TEXT,
  -- e.g. paper title, user action
  metadata JSONB DEFAULT '{}',
  recorded_at TIMESTAMPTZ DEFAULT now()
);

-- Graph change log: every modification to the knowledge graph
CREATE TABLE graph_changelog (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  change_type TEXT NOT NULL
    CHECK (change_type IN (
      'concept_added', 'concept_edited', 'concept_removed',
      'relationship_added', 'relationship_edited', 'relationship_removed',
      'claim_added', 'claim_edited', 'confidence_updated',
      'community_proposal_accepted', 'community_proposal_rejected'
    )),
  target_type TEXT NOT NULL
    CHECK (target_type IN ('concept', 'relationship', 'claim', 'paper')),
  target_id UUID NOT NULL,
  target_name TEXT,
  -- Snapshot for display
  changed_by TEXT NOT NULL
    CHECK (changed_by IN ('ai_pipeline', 'user_proposal', 'community_vote', 'admin', 'enrichment')),
  changed_by_id UUID,
  -- User or pipeline ID
  old_value JSONB,
  new_value JSONB,
  reason TEXT,
  recorded_at TIMESTAMPTZ DEFAULT now()
);

-- Field evolution milestones: paradigm shifts, key moments
CREATE TABLE field_milestones (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  title TEXT NOT NULL,
  description TEXT,
  milestone_type TEXT NOT NULL
    CHECK (milestone_type IN ('paradigm_shift', 'breakthrough', 'controversy',
                              'synthesis', 'split', 'decline', 'emergence')),
  year INT NOT NULL,
  month INT,
  -- Optional month precision
  related_concepts UUID[] DEFAULT '{}',
  related_papers UUID[] DEFAULT '{}',
  significance FLOAT DEFAULT 0.5
    CHECK (significance BETWEEN 0 AND 1),
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes
CREATE INDEX idx_concept_history_concept ON concept_history(concept_id);
CREATE INDEX idx_concept_history_time ON concept_history(recorded_at);
CREATE INDEX idx_graph_changelog_type ON graph_changelog(change_type);
CREATE INDEX idx_graph_changelog_target ON graph_changelog(target_type, target_id);
CREATE INDEX idx_graph_changelog_time ON graph_changelog(recorded_at DESC);
CREATE INDEX idx_field_milestones_year ON field_milestones(year);
CREATE INDEX idx_field_milestones_type ON field_milestones(milestone_type);
