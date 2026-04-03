-- =============================================
-- KORCZAK AI — Multi-Source Validation Schema
-- Migration 003: Validation & monitoring tables
-- =============================================

-- Source evidence: which sources confirmed what
CREATE TABLE source_evidence (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  element_type TEXT NOT NULL
    CHECK (element_type IN ('concept', 'relationship', 'paper', 'entity')),
  element_id TEXT NOT NULL,
  source_name TEXT NOT NULL,
  source_id TEXT,
  signal_type TEXT NOT NULL
    CHECK (signal_type IN ('confirms', 'contradicts', 'enriches')),
  signal_value FLOAT CHECK (signal_value BETWEEN 0 AND 1),
  signal_detail JSONB DEFAULT '{}',
  fetched_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(element_type, element_id, source_name, signal_type)
);

-- Quality flags: issues detected
CREATE TABLE quality_flags (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  element_type TEXT NOT NULL,
  element_id TEXT NOT NULL,
  flag_type TEXT NOT NULL,
  severity TEXT NOT NULL
    CHECK (severity IN ('low', 'medium', 'high', 'critical')),
  detail TEXT,
  suggested_action TEXT,
  status TEXT DEFAULT 'active'
    CHECK (status IN ('active', 'resolved', 'dismissed')),
  created_by TEXT DEFAULT 'pipeline',
  resolved_by UUID REFERENCES auth.users(id),
  resolved_at TIMESTAMPTZ,
  resolution_notes TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Source disagreements: when sources conflict
CREATE TABLE source_disagreements (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  element_type TEXT NOT NULL,
  element_id TEXT NOT NULL,
  source_a TEXT NOT NULL,
  source_a_value JSONB NOT NULL,
  source_b TEXT NOT NULL,
  source_b_value JSONB NOT NULL,
  disagreement_type TEXT NOT NULL,
  details JSONB DEFAULT '{}',
  resolution TEXT,
  resolution_source TEXT,
  surfaced_to_users BOOLEAN DEFAULT false,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Source health: are our data sources working?
CREATE TABLE source_health (
  source_name TEXT PRIMARY KEY,
  last_successful_fetch TIMESTAMPTZ,
  last_error TEXT,
  last_error_at TIMESTAMPTZ,
  success_rate_24h FLOAT DEFAULT 1.0,
  avg_latency_ms INT DEFAULT 0,
  error_count_24h INT DEFAULT 0,
  fetch_count_24h INT DEFAULT 0,
  status TEXT DEFAULT 'healthy'
    CHECK (status IN ('healthy', 'degraded', 'down')),
  rate_limit_remaining INT,
  rate_limit_resets_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes
CREATE INDEX idx_source_evidence_element ON source_evidence(element_type, element_id);
CREATE INDEX idx_source_evidence_source ON source_evidence(source_name);
CREATE INDEX idx_quality_flags_active ON quality_flags(element_type, element_id) WHERE status = 'active';
CREATE INDEX idx_quality_flags_severity ON quality_flags(severity) WHERE status = 'active';
CREATE INDEX idx_disagreements_element ON source_disagreements(element_type, element_id);
