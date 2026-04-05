-- Migration 011: Personal Knowledge Tree
-- Every user grows their own tree of knowledge

-- Knowledge tree nodes — user's personal tree structure
CREATE TABLE IF NOT EXISTS knowledge_tree_nodes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    concept_id UUID NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
    parent_node_id UUID REFERENCES knowledge_tree_nodes(id) ON DELETE SET NULL,
    depth INT DEFAULT 0,
    status TEXT DEFAULT 'locked' CHECK (status IN ('locked', 'available', 'in_progress', 'completed')),
    unlocked_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    branch_label TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(user_id, concept_id)
);

-- Branch choices — which path the user chose at each fork
CREATE TABLE IF NOT EXISTS branch_choices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    branch_point_concept_id UUID NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
    chosen_branch_concept_id UUID NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
    chosen_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(user_id, branch_point_concept_id)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_tree_nodes_user ON knowledge_tree_nodes(user_id);
CREATE INDEX IF NOT EXISTS idx_tree_nodes_parent ON knowledge_tree_nodes(parent_node_id);
CREATE INDEX IF NOT EXISTS idx_tree_nodes_status ON knowledge_tree_nodes(user_id, status);
CREATE INDEX IF NOT EXISTS idx_tree_nodes_depth ON knowledge_tree_nodes(user_id, depth);
CREATE INDEX IF NOT EXISTS idx_branch_choices_user ON branch_choices(user_id);
