-- Migration 005: Add behavior_data column for User Graph Layer 3
-- Stores session patterns, learning velocity, engagement metrics as JSONB

ALTER TABLE user_profiles
  ADD COLUMN IF NOT EXISTS behavior_data JSONB DEFAULT '{}';

-- Add comment for documentation
COMMENT ON COLUMN user_profiles.behavior_data IS 'Layer 3: behavioral patterns — sessions, hour_counts, mode_counts, avg_msg_len, concepts_seen';
