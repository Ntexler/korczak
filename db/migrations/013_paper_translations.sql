-- =============================================
-- KORCZAK AI — Paper Translations
-- Migration 013: Cache translated papers
-- =============================================

-- Cached translations of paper content
CREATE TABLE paper_translations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  paper_id UUID NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
  source_language TEXT NOT NULL DEFAULT 'en',
  target_language TEXT NOT NULL,
  translated_title TEXT,
  translated_abstract TEXT,
  translated_claims JSONB DEFAULT '[]',
  -- [{original: "...", translated: "..."}]
  translator_model TEXT,
  -- e.g. 'claude-sonnet-4-6'
  quality_score FLOAT,
  -- Self-assessed quality 0-1
  flagged BOOLEAN DEFAULT false,
  -- User flagged as poor translation
  created_at TIMESTAMPTZ DEFAULT now(),

  -- One translation per paper per target language
  UNIQUE(paper_id, target_language)
);

CREATE INDEX idx_paper_translations_paper ON paper_translations(paper_id);
CREATE INDEX idx_paper_translations_lang ON paper_translations(target_language);
