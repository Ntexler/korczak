-- =============================================
-- KORCZAK AI — Navigator RPCs
-- Migration 004: Graph traversal functions
-- =============================================

-- get_concept_neighborhood: recursive CTE walking relationships bidirectionally
-- Returns connected concepts with relationship type + confidence
CREATE OR REPLACE FUNCTION get_concept_neighborhood(
  p_concept_id UUID,
  p_depth INT DEFAULT 1
)
RETURNS TABLE (
  concept_id UUID,
  concept_name TEXT,
  concept_type TEXT,
  concept_definition TEXT,
  concept_confidence FLOAT,
  relationship_type TEXT,
  relationship_confidence FLOAT,
  relationship_explanation TEXT,
  depth INT
) AS $$
BEGIN
  RETURN QUERY
  WITH RECURSIVE neighborhood AS (
    -- Base case: direct neighbors (outgoing)
    SELECT
      c.id AS concept_id,
      c.name AS concept_name,
      c.type AS concept_type,
      c.definition AS concept_definition,
      c.confidence AS concept_confidence,
      r.relationship_type,
      r.confidence AS relationship_confidence,
      r.explanation AS relationship_explanation,
      1 AS depth
    FROM relationships r
    JOIN concepts c ON c.id = r.target_id
    WHERE r.source_id = p_concept_id
      AND r.source_type = 'concept'
      AND r.target_type = 'concept'

    UNION

    -- Base case: direct neighbors (incoming)
    SELECT
      c.id AS concept_id,
      c.name AS concept_name,
      c.type AS concept_type,
      c.definition AS concept_definition,
      c.confidence AS concept_confidence,
      r.relationship_type,
      r.confidence AS relationship_confidence,
      r.explanation AS relationship_explanation,
      1 AS depth
    FROM relationships r
    JOIN concepts c ON c.id = r.source_id
    WHERE r.target_id = p_concept_id
      AND r.source_type = 'concept'
      AND r.target_type = 'concept'

    UNION

    -- Recursive case: walk further (only if depth < p_depth)
    SELECT
      c.id,
      c.name,
      c.type,
      c.definition,
      c.confidence,
      r.relationship_type,
      r.confidence,
      r.explanation,
      n.depth + 1
    FROM neighborhood n
    JOIN relationships r ON (
      (r.source_id = n.concept_id AND r.source_type = 'concept' AND r.target_type = 'concept')
      OR
      (r.target_id = n.concept_id AND r.source_type = 'concept' AND r.target_type = 'concept')
    )
    JOIN concepts c ON c.id = CASE
      WHEN r.source_id = n.concept_id THEN r.target_id
      ELSE r.source_id
    END
    WHERE n.depth < p_depth
      AND c.id != p_concept_id  -- Don't loop back to origin
  )
  SELECT DISTINCT ON (neighborhood.concept_id)
    neighborhood.concept_id,
    neighborhood.concept_name,
    neighborhood.concept_type,
    neighborhood.concept_definition,
    neighborhood.concept_confidence,
    neighborhood.relationship_type,
    neighborhood.relationship_confidence,
    neighborhood.relationship_explanation,
    neighborhood.depth
  FROM neighborhood
  ORDER BY neighborhood.concept_id, neighborhood.depth ASC;
END;
$$ LANGUAGE plpgsql;
