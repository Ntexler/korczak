-- Migration 017: Paper uploads quality pipeline
-- Track user-uploaded papers through verification and quality assessment

CREATE TABLE paper_uploads (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  -- Who uploaded
  uploaded_by TEXT, -- user ID (nullable for anonymous)
  -- File info
  original_filename TEXT NOT NULL,
  file_size_bytes INT,
  -- Extracted content
  extracted_text TEXT,
  extracted_title TEXT,
  extracted_authors TEXT,
  extracted_doi TEXT,
  -- Verification
  doi_verified BOOLEAN DEFAULT false,
  crossref_data JSONB DEFAULT '{}',
  journal_name TEXT,
  journal_flagged BOOLEAN DEFAULT false, -- predatory journal warning
  -- Quality gate
  quality_score FLOAT, -- 0-1 from Claude assessment
  quality_assessment JSONB DEFAULT '{}', -- detailed breakdown
  quality_status TEXT NOT NULL DEFAULT 'pending'
    CHECK (quality_status IN ('pending', 'processing', 'approved', 'quarantined', 'rejected', 'duplicate')),
  rejection_reason TEXT,
  -- Link to papers table if approved
  paper_id UUID REFERENCES papers(id),
  -- Timestamps
  created_at TIMESTAMPTZ DEFAULT now(),
  processed_at TIMESTAMPTZ,
  approved_at TIMESTAMPTZ
);

CREATE INDEX idx_paper_uploads_status ON paper_uploads(quality_status);
CREATE INDEX idx_paper_uploads_user ON paper_uploads(uploaded_by);
CREATE INDEX idx_paper_uploads_doi ON paper_uploads(extracted_doi);
