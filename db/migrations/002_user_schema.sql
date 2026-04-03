-- =============================================
-- KORCZAK AI — User Graph Schema
-- Migration 002: User tables
-- =============================================

-- User profiles (extends Supabase auth.users)
CREATE TABLE user_profiles (
  user_id UUID PRIMARY KEY REFERENCES auth.users(id),

  -- Identity
  display_name TEXT,
  language TEXT DEFAULT 'en',

  -- Context (Layer 2 — populated later)
  role TEXT,
  -- 'undergrad','doctoral','postdoc','faculty','r_and_d','independent'
  institution TEXT,
  department TEXT,
  advisor_name TEXT,
  research_topic TEXT,
  research_stage TEXT,
  -- 'exploring','proposal','data_collection','writing'
  upcoming_deadlines JSONB DEFAULT '[]',

  -- Connected accounts (optional)
  orcid_id TEXT,
  google_scholar_id TEXT,

  -- Patterns (Layer 3 — auto-updated, populated later)
  thinking_style JSONB DEFAULT '{
    "analogical": 0.5, "quantitative": 0.5,
    "visual": 0.5, "theoretical": 0.5, "practical": 0.5
  }',
  work_pattern JSONB DEFAULT '{
    "session_frequency": "unknown",
    "avg_session_length_min": 0,
    "question_style": "unknown",
    "depth_preference": "unknown"
  }',
  motivation TEXT,
  risk_tolerance TEXT,
  time_availability TEXT,

  -- Learned preferences
  preferred_socratic_level INT DEFAULT 1,
  prefers_direct_answers BOOLEAN DEFAULT false,
  prefers_proactive_suggestions BOOLEAN DEFAULT true,

  -- Relationship memory
  topics_discussed JSONB DEFAULT '[]',
  promises_made JSONB DEFAULT '[]',

  -- Meta
  session_count INT DEFAULT 0,
  first_seen TIMESTAMPTZ DEFAULT now(),
  last_seen TIMESTAMPTZ DEFAULT now()
);

-- User knowledge state (Layer 1 — MVP)
CREATE TABLE user_knowledge (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  concept_id UUID NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,

  understanding_level FLOAT DEFAULT 0
    CHECK (understanding_level BETWEEN 0 AND 1),
  -- 0 = never encountered, 1 = expert

  misconceptions JSONB DEFAULT '[]',
  -- [{misconception, detected_at, corrected: bool}]

  blind_spots JSONB DEFAULT '[]',
  -- [{related_concept_id, description}]

  analogies_used JSONB DEFAULT '[]',
  -- [{analogy_text, effective: bool}]

  last_interaction TIMESTAMPTZ DEFAULT now(),
  interaction_count INT DEFAULT 1,

  UNIQUE(user_id, concept_id)
);

-- Conversations
CREATE TABLE conversations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,

  mode TEXT DEFAULT 'navigator'
    CHECK (mode IN ('navigator', 'tutor', 'briefing')),

  title TEXT,
  -- Auto-generated from first message

  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Messages within conversations
CREATE TABLE messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,

  role TEXT NOT NULL
    CHECK (role IN ('user', 'assistant', 'system')),
  content TEXT NOT NULL,

  -- Navigator metadata
  graph_context JSONB,
  -- What graph nodes were used to generate this response
  concepts_referenced JSONB DEFAULT '[]',
  -- [{concept_id, relevance}]

  -- Quality tracking
  hallucination_checked BOOLEAN DEFAULT false,
  hallucination_score FLOAT,

  created_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes
CREATE INDEX idx_user_knowledge_user ON user_knowledge(user_id);
CREATE INDEX idx_user_knowledge_concept ON user_knowledge(concept_id);
CREATE INDEX idx_conversations_user ON conversations(user_id);
CREATE INDEX idx_messages_conversation ON messages(conversation_id);
CREATE INDEX idx_messages_created ON messages(created_at);
