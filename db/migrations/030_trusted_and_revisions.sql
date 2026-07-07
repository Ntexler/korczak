-- Migration 030: Trusted sources registry + belief-revision memory
-- Run in Supabase SQL Editor

-- ── Trusted sources (user-approved list, admin-managed) ──
CREATE TABLE IF NOT EXISTS trusted_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    tier INT NOT NULL CHECK (tier IN (1, 2, 3)),
    -- 1 = peer-reviewed anchors (one witness counts as two)
    -- 2 = verified institutional data (facts, not interpretation)
    -- 3 = quality knowledge journalism / primary-text archives (validation only)
    domain_area TEXT,
    notes TEXT,
    added_by TEXT DEFAULT 'admin',
    created_at TIMESTAMPTZ DEFAULT now()
);

INSERT INTO trusted_sources (name, tier, domain_area) VALUES
    -- Tier 1: peer-reviewed anchors
    ('Science', 1, 'general'), ('Nature', 1, 'general'),
    ('Proceedings of the National Academy of Sciences', 1, 'general'), ('Cell', 1, 'general'),
    ('The Lancet', 1, 'medicine'), ('New England Journal of Medicine', 1, 'medicine'),
    ('JAMA', 1, 'medicine'), ('BMJ', 1, 'medicine'), ('Cochrane', 1, 'medicine'),
    ('Nature Neuroscience', 1, 'neuroscience'), ('Psychological Science', 1, 'psychology'),
    ('Behavioral and Brain Sciences', 1, 'psychology'),
    ('American Anthropologist', 1, 'anthropology'), ('Current Anthropology', 1, 'anthropology'),
    ('American Sociological Review', 1, 'sociology'),
    ('American Economic Review', 1, 'economics'), ('Quarterly Journal of Economics', 1, 'economics'),
    ('Econometrica', 1, 'economics'), ('American Political Science Review', 1, 'political science'),
    ('Stanford Encyclopedia of Philosophy', 1, 'philosophy'), ('Mind', 1, 'philosophy'),
    ('Journal of Philosophy', 1, 'philosophy'),
    ('American Historical Review', 1, 'history'), ('Past & Present', 1, 'history'),
    ('Language', 1, 'linguistics'),
    ('Harvard Law Review', 1, 'law'), ('Yale Law Journal', 1, 'law'),
    ('Annals of Mathematics', 1, 'mathematics'), ('Journal of the ACM', 1, 'computer science'),
    ('Nature Climate Change', 1, 'climate'), ('IPCC', 1, 'climate'),
    -- Tier 2: verified institutional data
    ('Our World in Data', 2, 'data'), ('Pew Research Center', 2, 'data'),
    ('OECD', 2, 'data'), ('World Bank', 2, 'data'),
    ('Israel Central Bureau of Statistics', 2, 'data'), ('Eurostat', 2, 'data'),
    -- Tier 3: quality knowledge journalism + primary-text archives
    ('Quanta Magazine', 3, 'science journalism'), ('Scientific American', 3, 'science journalism'),
    ('Science News', 3, 'science journalism'), ('Nature News', 3, 'science journalism'),
    ('The Conversation', 3, 'science journalism'), ('Aeon', 3, 'essays'),
    ('MIT Technology Review', 3, 'technology'),
    ('Project Gutenberg', 3, 'primary texts'), ('Perseus Digital Library', 3, 'primary texts'),
    ('Sefaria', 3, 'primary texts'), ('Ben-Yehuda Project', 3, 'primary texts'),
    ('Internet Archive', 3, 'archives')
ON CONFLICT (name) DO NOTHING;

-- ── Belief revisions: Chappie's intellectual biography ──
-- "I used to think X; paper Y changed my mind on <date>; here's why."
-- No knowledge system remembers the history of its own mistakes. This one does.
CREATE TABLE IF NOT EXISTS belief_revisions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_type TEXT NOT NULL CHECK (subject_type IN ('concept', 'proposition')),
    subject_id UUID,
    subject_name TEXT NOT NULL,
    field TEXT,
    old_belief TEXT NOT NULL,        -- what was believed (e.g. "consensus")
    new_belief TEXT NOT NULL,        -- what is believed now (e.g. "contested")
    reason TEXT,                     -- why the mind changed
    trigger_source TEXT,             -- what caused it: propagation / new_evidence / admin_revert / stance_shift
    trigger_ref TEXT,                -- paper title / enrichment id / journey id
    revised_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_belief_revisions_time ON belief_revisions (revised_at DESC);
CREATE INDEX IF NOT EXISTS idx_belief_revisions_subject ON belief_revisions (subject_type, subject_id);
