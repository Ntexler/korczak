-- Migration 028: Privacy layer for user uploads.
--
-- Implements the "transform, don't share" model: when a user uploads
-- a paper they obtained, full_text stays private to that uploader.
-- The Claude-derived analysis (concepts, claims, relationships) is
-- shared globally because it is transformative.
--
-- Two flags on papers:
--   uploaded_by   — the user who provided the original document
--   text_private  — when TRUE, the public API must not expose
--                   full_text or abstract verbatim to non-owners.
--                   Analysis fields remain public.

ALTER TABLE papers
    ADD COLUMN IF NOT EXISTS uploaded_by UUID,
    ADD COLUMN IF NOT EXISTS text_private BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS upload_id UUID REFERENCES paper_uploads(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS papers_uploaded_by_idx ON papers(uploaded_by) WHERE uploaded_by IS NOT NULL;
CREATE INDEX IF NOT EXISTS papers_text_private_idx ON papers(text_private) WHERE text_private = TRUE;
