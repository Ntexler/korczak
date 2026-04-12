-- Migration 019: Course Engine — reading scores, generated courses, feedback protection
-- Run in Supabase SQL Editor

-- 1. Expand syllabi source CHECK to include new sources
ALTER TABLE syllabi DROP CONSTRAINT IF EXISTS syllabi_source_check;
ALTER TABLE syllabi ADD CONSTRAINT syllabi_source_check
    CHECK (source IN ('mit_ocw', 'openstax', 'custom', 'other',
                      'open_syllabus', 'harvard', 'stanford', 'coursera', 'edx'));

-- 2. Reading scores — cached cross-syllabus analysis
CREATE TABLE IF NOT EXISTS reading_scores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    paper_id UUID REFERENCES papers(id) ON DELETE SET NULL,
    reading_title TEXT NOT NULL,
    department TEXT NOT NULL,
    frequency_score FLOAT DEFAULT 0,
    institution_diversity FLOAT DEFAULT 0,
    position_score FLOAT DEFAULT 0,
    citation_weight FLOAT DEFAULT 0,
    teaching_score FLOAT DEFAULT 0,
    user_adjustment FLOAT DEFAULT 0,
    combined_score FLOAT DEFAULT 0,
    tier TEXT CHECK (tier IN ('canonical', 'important', 'specialized', 'niche', 'ai_recommended')) DEFAULT 'niche',
    source_count INT DEFAULT 0,
    source_institutions TEXT[] DEFAULT '{}',
    authors TEXT DEFAULT '',
    publication_year INT,
    ai_rationale TEXT,
    computed_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_reading_scores_dept_score
    ON reading_scores (department, combined_score DESC);
CREATE INDEX IF NOT EXISTS idx_reading_scores_tier
    ON reading_scores (tier);
CREATE INDEX IF NOT EXISTS idx_reading_scores_paper
    ON reading_scores (paper_id) WHERE paper_id IS NOT NULL;

-- 3. Generated courses
CREATE TABLE IF NOT EXISTS generated_courses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    department TEXT NOT NULL,
    level TEXT CHECK (level IN ('intro', 'intermediate', 'advanced', 'graduate')) NOT NULL,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    methodology TEXT DEFAULT '',
    weeks JSONB DEFAULT '[]'::jsonb,
    source_syllabi_count INT DEFAULT 0,
    reading_count INT DEFAULT 0,
    ai_recommendations_count INT DEFAULT 0,
    generated_model TEXT,
    is_published BOOLEAN DEFAULT false,
    generated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_generated_courses_dept
    ON generated_courses (department, level);

-- 4. Course readings — individual readings within generated courses
CREATE TABLE IF NOT EXISTS course_readings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    course_id UUID NOT NULL REFERENCES generated_courses(id) ON DELETE CASCADE,
    paper_id UUID REFERENCES papers(id) ON DELETE SET NULL,
    reading_title TEXT NOT NULL,
    week INT NOT NULL,
    position INT DEFAULT 0,
    section TEXT CHECK (section IN ('required', 'recommended', 'supplementary')) DEFAULT 'required',
    combined_score FLOAT DEFAULT 0,
    tier TEXT DEFAULT 'niche',
    rationale TEXT,
    is_ai_recommended BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_course_readings_course
    ON course_readings (course_id, week, position);

-- 5. Reading feedback — user votes with abuse protection metadata
CREATE TABLE IF NOT EXISTS reading_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    course_reading_id UUID NOT NULL REFERENCES course_readings(id) ON DELETE CASCADE,
    vote_type TEXT CHECK (vote_type IN ('upvote', 'downvote')) NOT NULL,
    vote_weight FLOAT DEFAULT 1.0,
    is_suspicious BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (user_id, course_reading_id)
);

CREATE INDEX IF NOT EXISTS idx_reading_feedback_reading
    ON reading_feedback (course_reading_id);
CREATE INDEX IF NOT EXISTS idx_reading_feedback_user_daily
    ON reading_feedback (user_id, created_at);
