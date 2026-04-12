-- Migration 018: Search Pipeline — full-text search + embedding RPCs
-- Run in Supabase SQL Editor

-- 1. Add tsvector column to papers for full-text search
ALTER TABLE papers ADD COLUMN IF NOT EXISTS search_vector tsvector;

-- 2. Backfill existing papers
UPDATE papers SET search_vector =
    setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
    setweight(to_tsvector('english', coalesce(abstract, '')), 'B') ||
    setweight(to_tsvector('english', coalesce(full_text, '')), 'C');

-- 3. Auto-update trigger
CREATE OR REPLACE FUNCTION papers_search_vector_update() RETURNS trigger AS $$
BEGIN
    NEW.search_vector :=
        setweight(to_tsvector('english', coalesce(NEW.title, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(NEW.abstract, '')), 'B') ||
        setweight(to_tsvector('english', coalesce(NEW.full_text, '')), 'C');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS papers_search_vector_trigger ON papers;
CREATE TRIGGER papers_search_vector_trigger
    BEFORE INSERT OR UPDATE OF title, abstract, full_text
    ON papers
    FOR EACH ROW
    EXECUTE FUNCTION papers_search_vector_update();

-- 4. GIN index for fast full-text search
CREATE INDEX IF NOT EXISTS idx_papers_search_vector ON papers USING GIN (search_vector);

-- 5. RPC: Full-text search on papers
CREATE OR REPLACE FUNCTION fulltext_search_papers(
    search_query TEXT,
    match_count INT DEFAULT 10
)
RETURNS TABLE (
    id UUID,
    title TEXT,
    abstract TEXT,
    authors JSONB,
    publication_year INT,
    cited_by_count INT,
    source_journal TEXT,
    rank FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        p.id,
        p.title,
        p.abstract,
        p.authors,
        p.publication_year,
        p.cited_by_count,
        p.source_journal,
        ts_rank_cd(p.search_vector, websearch_to_tsquery('english', search_query))::FLOAT AS rank
    FROM papers p
    WHERE p.search_vector @@ websearch_to_tsquery('english', search_query)
    ORDER BY rank DESC
    LIMIT match_count;
END;
$$ LANGUAGE plpgsql;

-- 6. RPC: Semantic search on concepts via pgvector
CREATE OR REPLACE FUNCTION search_concepts_by_embedding(
    query_embedding vector(1536),
    match_threshold FLOAT DEFAULT 0.7,
    match_count INT DEFAULT 10
)
RETURNS TABLE (
    id UUID,
    name TEXT,
    type TEXT,
    definition TEXT,
    confidence FLOAT,
    paper_count INT,
    trend TEXT,
    similarity FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        c.id,
        c.name,
        c.type,
        c.definition,
        c.confidence::FLOAT,
        c.paper_count,
        c.trend,
        (1 - (c.embedding <=> query_embedding))::FLOAT AS similarity
    FROM concepts c
    WHERE c.embedding IS NOT NULL
      AND (1 - (c.embedding <=> query_embedding)) >= match_threshold
    ORDER BY c.embedding <=> query_embedding
    LIMIT match_count;
END;
$$ LANGUAGE plpgsql;

-- 7. RPC: Semantic search on claims via pgvector
CREATE OR REPLACE FUNCTION search_claims_by_embedding(
    query_embedding vector(1536),
    match_threshold FLOAT DEFAULT 0.6,
    match_count INT DEFAULT 10
)
RETURNS TABLE (
    id UUID,
    paper_id UUID,
    claim_text TEXT,
    evidence_type TEXT,
    strength TEXT,
    confidence FLOAT,
    similarity FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        cl.id,
        cl.paper_id,
        cl.claim_text,
        cl.evidence_type,
        cl.strength,
        cl.confidence::FLOAT,
        (1 - (cl.embedding <=> query_embedding))::FLOAT AS similarity
    FROM claims cl
    WHERE cl.embedding IS NOT NULL
      AND (1 - (cl.embedding <=> query_embedding)) >= match_threshold
    ORDER BY cl.embedding <=> query_embedding
    LIMIT match_count;
END;
$$ LANGUAGE plpgsql;
