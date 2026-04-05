-- Migration 008: Syllabi — templates, readings, and user customizations
-- Supports MIT OCW, OpenStax, and custom syllabi

-- Template syllabi (scraped or manually created)
CREATE TABLE IF NOT EXISTS syllabi (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,
    course_code TEXT,
    institution TEXT,
    department TEXT,
    instructor TEXT,
    year INT,
    url TEXT,
    concept_ids UUID[] DEFAULT '{}',
    paper_count INT DEFAULT 0,
    source TEXT DEFAULT 'custom' CHECK (source IN ('mit_ocw', 'openstax', 'custom', 'other')),
    license TEXT,
    is_template BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Syllabus readings (matched or unmatched to DB papers)
CREATE TABLE IF NOT EXISTS syllabus_readings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    syllabus_id UUID NOT NULL REFERENCES syllabi(id) ON DELETE CASCADE,
    paper_id UUID REFERENCES papers(id) ON DELETE SET NULL,
    external_title TEXT,
    external_authors TEXT,
    external_year INT,
    external_doi TEXT,
    week INT,
    section TEXT DEFAULT 'required' CHECK (section IN ('required', 'recommended', 'supplementary')),
    position INT DEFAULT 0,
    match_confidence FLOAT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- User's customized syllabi (forked from templates or created from scratch)
CREATE TABLE IF NOT EXISTS user_syllabi (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    syllabus_id UUID REFERENCES syllabi(id) ON DELETE SET NULL,
    custom_title TEXT,
    custom_topics JSONB DEFAULT '{}'::jsonb,
    progress JSONB DEFAULT '{}'::jsonb,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_syllabi_source ON syllabi(source);
CREATE INDEX IF NOT EXISTS idx_syllabi_department ON syllabi(department);
CREATE INDEX IF NOT EXISTS idx_syllabi_institution ON syllabi(institution);
CREATE INDEX IF NOT EXISTS idx_syllabi_template ON syllabi(is_template) WHERE is_template = true;
CREATE INDEX IF NOT EXISTS idx_syllabus_readings_syllabus ON syllabus_readings(syllabus_id);
CREATE INDEX IF NOT EXISTS idx_syllabus_readings_paper ON syllabus_readings(paper_id);
CREATE INDEX IF NOT EXISTS idx_user_syllabi_user ON user_syllabi(user_id);
CREATE INDEX IF NOT EXISTS idx_user_syllabi_active ON user_syllabi(user_id, is_active) WHERE is_active = true;

-- Updated_at triggers
CREATE TRIGGER syllabi_updated_at
    BEFORE UPDATE ON syllabi
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER user_syllabi_updated_at
    BEFORE UPDATE ON user_syllabi
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
