-- =============================================
-- KORCZAK AI — Core Knowledge Graph Schema
-- Migration 001: Core tables
-- =============================================

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";

-- =============================================
-- KNOWLEDGE GRAPH TABLES
-- =============================================

-- Papers: source documents
CREATE TABLE papers (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  openalex_id TEXT UNIQUE,
  doi TEXT,
  title TEXT NOT NULL,
  authors JSONB DEFAULT '[]',
  -- [{name, openalex_id, orcid, institution}]
  publication_year INT,
  abstract TEXT,
  paper_type TEXT,
  -- 'original_research','review','meta_analysis','theoretical','methodological','commentary','book_chapter'
  subfield TEXT,
  source_journal TEXT,
  cited_by_count INT DEFAULT 0,

  -- Analysis
  analysis JSONB,
  -- Full Claude analysis output (concepts, relationships, claims, etc.)
  analysis_model TEXT,
  -- Which model produced the analysis
  analyzed_at TIMESTAMPTZ,

  -- Metadata
  language TEXT DEFAULT 'en',
  open_access BOOLEAN,
  funding JSONB DEFAULT '[]',
  -- [{funder, grant_id, amount}]

  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Concepts: ideas, theories, methods, phenomena
CREATE TABLE concepts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  normalized_name TEXT NOT NULL,
  -- Lowercase, stripped for dedup matching
  type TEXT NOT NULL
    CHECK (type IN ('theory', 'method', 'framework', 'phenomenon', 'tool', 'metric', 'critique', 'paradigm')),
  definition TEXT,

  -- Vitals
  paper_count INT DEFAULT 0,
  rate_of_change FLOAT DEFAULT 0,
  -- Papers/year rate
  trend TEXT DEFAULT 'stable'
    CHECK (trend IN ('rising', 'stable', 'declining', 'emerging', 'dormant')),
  controversy_score FLOAT DEFAULT 0
    CHECK (controversy_score BETWEEN 0 AND 1),
  interdisciplinarity FLOAT DEFAULT 0
    CHECK (interdisciplinarity BETWEEN 0 AND 1),

  -- Embeddings for entity resolution + semantic search
  embedding vector(1536),
  -- OpenAI text-embedding-3-small

  -- Confidence & validation
  confidence FLOAT DEFAULT 0.5
    CHECK (confidence BETWEEN 0 AND 1),
  source_count INT DEFAULT 1,
  last_validated TIMESTAMPTZ,

  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Claims: specific assertions from papers
CREATE TABLE claims (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  paper_id UUID NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
  claim_text TEXT NOT NULL,
  evidence_type TEXT
    CHECK (evidence_type IN ('empirical', 'theoretical', 'comparative', 'methodological', 'meta_analytic')),
  strength TEXT DEFAULT 'moderate'
    CHECK (strength IN ('strong', 'moderate', 'weak')),
  testable BOOLEAN DEFAULT false,

  -- Validation
  confidence FLOAT DEFAULT 0.5,
  supporting_papers INT DEFAULT 0,
  contradicting_papers INT DEFAULT 0,

  embedding vector(1536),

  created_at TIMESTAMPTZ DEFAULT now()
);

-- Entities: people, institutions, journals
CREATE TABLE entities (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  normalized_name TEXT NOT NULL,
  type TEXT NOT NULL
    CHECK (type IN ('person', 'institution', 'journal', 'funder', 'conference')),

  -- External IDs
  openalex_id TEXT,
  orcid TEXT,
  ror_id TEXT,
  -- Research Organization Registry

  metadata JSONB DEFAULT '{}',
  -- Type-specific: h_index, country, field, etc.

  embedding vector(1536),

  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Controversies: active debates in the field
CREATE TABLE controversies (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  title TEXT NOT NULL,
  description TEXT,
  status TEXT DEFAULT 'active'
    CHECK (status IN ('active', 'resolved', 'dormant', 'emerging')),

  -- Sides of the debate
  sides JSONB DEFAULT '[]',
  -- [{label, key_proponents: [entity_ids], key_papers: [paper_ids], evidence_summary}]

  -- Vitals
  intensity FLOAT DEFAULT 0.5,
  first_appeared TIMESTAMPTZ,
  last_activity TIMESTAMPTZ,
  paper_count INT DEFAULT 0,

  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- =============================================
-- RELATIONSHIPS (EDGES)
-- =============================================

CREATE TABLE relationships (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  -- Source and target can be any node type
  source_type TEXT NOT NULL
    CHECK (source_type IN ('paper', 'concept', 'claim', 'entity', 'controversy')),
  source_id UUID NOT NULL,
  target_type TEXT NOT NULL
    CHECK (target_type IN ('paper', 'concept', 'claim', 'entity', 'controversy')),
  target_id UUID NOT NULL,

  -- Edge type
  relationship_type TEXT NOT NULL
    CHECK (relationship_type IN (
      'BUILDS_ON', 'CONTRADICTS', 'EXTENDS', 'APPLIES',
      'ANALOGOUS_TO', 'PART_OF', 'PREREQUISITE_FOR',
      'FUNDED_BY', 'TAUGHT_IN', 'AUTHORED_BY', 'RESPONDS_TO',
      'INTRODUCES', 'CITES', 'SUPPORTS', 'WEAKENS'
    )),

  -- Metadata
  confidence FLOAT DEFAULT 0.5
    CHECK (confidence BETWEEN 0 AND 1),
  explanation TEXT,
  paper_id UUID REFERENCES papers(id),
  -- The paper that established this relationship

  -- Confidence decay
  last_reinforced TIMESTAMPTZ DEFAULT now(),
  decay_rate FLOAT DEFAULT 0.05,
  -- Per year, never below 0.3

  created_at TIMESTAMPTZ DEFAULT now()
);

-- Paper-concept junction (which concepts appear in which papers)
CREATE TABLE paper_concepts (
  paper_id UUID NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
  concept_id UUID NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
  relevance FLOAT DEFAULT 0.5,
  novelty_in_paper TEXT DEFAULT 'low'
    CHECK (novelty_in_paper IN ('high', 'medium', 'low')),
  well_established BOOLEAN DEFAULT true,
  PRIMARY KEY (paper_id, concept_id)
);

-- =============================================
-- INDEXES
-- =============================================

-- Papers
CREATE INDEX idx_papers_openalex ON papers(openalex_id);
CREATE INDEX idx_papers_year ON papers(publication_year);
CREATE INDEX idx_papers_subfield ON papers(subfield);

-- Concepts
CREATE INDEX idx_concepts_name ON concepts(normalized_name);
CREATE INDEX idx_concepts_type ON concepts(type);
CREATE INDEX idx_concepts_trend ON concepts(trend);
CREATE INDEX idx_concepts_embedding ON concepts
  USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Claims
CREATE INDEX idx_claims_paper ON claims(paper_id);
CREATE INDEX idx_claims_embedding ON claims
  USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Entities
CREATE INDEX idx_entities_name ON entities(normalized_name);
CREATE INDEX idx_entities_type ON entities(type);
CREATE INDEX idx_entities_openalex ON entities(openalex_id);

-- Relationships
CREATE INDEX idx_rel_source ON relationships(source_type, source_id);
CREATE INDEX idx_rel_target ON relationships(target_type, target_id);
CREATE INDEX idx_rel_type ON relationships(relationship_type);

-- Paper-concepts
CREATE INDEX idx_pc_concept ON paper_concepts(concept_id);
