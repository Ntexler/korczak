-- Migration 009: Syllabus RPCs
-- Graph-aware functions for syllabus concept mapping and progress tracking

-- Get syllabus graph data with centrality and user progress
CREATE OR REPLACE FUNCTION get_syllabus_graph(
    p_syllabus_id UUID,
    p_user_id UUID DEFAULT NULL
)
RETURNS TABLE (
    concept_id UUID,
    concept_name TEXT,
    concept_type TEXT,
    in_degree INT,
    out_degree INT,
    is_pillar BOOLEAN,
    user_level INT,
    dependent_count INT
) AS $$
BEGIN
    RETURN QUERY
    WITH syllabus_concepts AS (
        -- Get concepts from syllabus readings
        SELECT DISTINCT pc.concept_id
        FROM syllabus_readings sr
        JOIN paper_concepts pc ON pc.paper_id = sr.paper_id
        WHERE sr.syllabus_id = p_syllabus_id
          AND sr.paper_id IS NOT NULL
    ),
    concept_degrees AS (
        -- Compute in-degree and out-degree for syllabus concepts
        SELECT
            sc.concept_id,
            COALESCE(SUM(CASE WHEN r.target_id = sc.concept_id THEN 1 ELSE 0 END), 0)::INT AS in_deg,
            COALESCE(SUM(CASE WHEN r.source_id = sc.concept_id THEN 1 ELSE 0 END), 0)::INT AS out_deg
        FROM syllabus_concepts sc
        LEFT JOIN relationships r ON (r.source_id = sc.concept_id OR r.target_id = sc.concept_id)
            AND r.relationship_type IN ('BUILDS_ON', 'PREREQUISITE_FOR', 'RELATES')
        GROUP BY sc.concept_id
    ),
    dependents AS (
        -- Count how many concepts depend on each concept
        SELECT
            r.source_id AS concept_id,
            COUNT(DISTINCT r.target_id)::INT AS dep_count
        FROM relationships r
        WHERE r.source_id IN (SELECT concept_id FROM syllabus_concepts)
          AND r.relationship_type IN ('BUILDS_ON', 'PREREQUISITE_FOR')
        GROUP BY r.source_id
    )
    SELECT
        c.id AS concept_id,
        c.name AS concept_name,
        c.type AS concept_type,
        COALESCE(cd.in_deg, 0) AS in_degree,
        COALESCE(cd.out_deg, 0) AS out_degree,
        (COALESCE(cd.in_deg, 0) + COALESCE(d.dep_count, 0) > 5) AS is_pillar,
        COALESCE(uk.understanding_level, 0)::INT AS user_level,
        COALESCE(d.dep_count, 0) AS dependent_count
    FROM syllabus_concepts sc
    JOIN concepts c ON c.id = sc.concept_id
    LEFT JOIN concept_degrees cd ON cd.concept_id = sc.concept_id
    LEFT JOIN dependents d ON d.concept_id = sc.concept_id
    LEFT JOIN user_knowledge uk ON uk.concept_id = sc.concept_id AND uk.user_id = p_user_id
    ORDER BY (COALESCE(cd.in_deg, 0) + COALESCE(d.dep_count, 0)) DESC;
END;
$$ LANGUAGE plpgsql;
