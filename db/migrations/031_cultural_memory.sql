-- Migration 031: Cultural memory — "not only science"
-- The history of ideas, primary texts, and the memory of scientific failures.
-- Run in Supabase SQL Editor

-- Works don't have to be journal articles. A work_kind lets primary texts,
-- historical documents, and scanned books live in the graph as first-class
-- sources alongside papers.
ALTER TABLE papers ADD COLUMN IF NOT EXISTS work_kind TEXT DEFAULT 'article'
    CHECK (work_kind IN ('article', 'book', 'primary_text', 'historical_document', 'essay', 'lecture'));
ALTER TABLE papers ADD COLUMN IF NOT EXISTS external_url TEXT;   -- reading-room link (e.g. archive.org)
ALTER TABLE papers ADD COLUMN IF NOT EXISTS has_fulltext BOOLEAN DEFAULT false;

CREATE INDEX IF NOT EXISTS idx_papers_work_kind ON papers (work_kind);

-- The memory of failure: how knowledge went wrong before, so we recognize
-- it going wrong again. Phlogiston, N-rays, the replication crisis…
CREATE TABLE IF NOT EXISTS knowledge_failures (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    field TEXT,
    era TEXT,                              -- "18th century", "1900s", "2010s"
    what_was_believed TEXT NOT NULL,
    why_it_was_compelling TEXT,            -- it looked right at the time
    how_it_fell TEXT,                      -- what evidence/logic ended it
    lesson TEXT,                           -- the transferable warning
    related_concepts TEXT[] DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now()
);

-- A few seed cases — the canonical cautionary tales of every field
INSERT INTO knowledge_failures (name, field, era, what_was_believed, why_it_was_compelling, how_it_fell, lesson) VALUES
    ('Phlogiston', 'Chemistry', '18th century',
     'Combustible materials contained a fire-substance ("phlogiston") released when burning.',
     'It elegantly explained why things lose mass or char when burned, and unified many observations.',
     'Lavoisier showed combustion GAINS mass by combining with oxygen — careful weighing killed it.',
     'An elegant theory that explains the known data can still be entirely wrong. Measure what the theory says shouldn''t change.'),
    ('N-rays', 'Physics', '1900s',
     'A new form of radiation ("N-rays") emitted by many materials, detected by faint changes in spark brightness.',
     'A respected physicist and dozens of papers reported them; people SAW the effect they expected.',
     'Robert Wood secretly removed the prism from the apparatus — the observer still "saw" N-rays. Pure expectation.',
     'When detection depends on human judgment of a faint signal, expectation manufactures the result. Blind the observer.'),
    ('Replication Crisis', 'Psychology', '2010s',
     'Many famous priming/social-psychology effects were robust, replicable facts.',
     'They were published in top journals, widely cited, and told compelling stories about human nature.',
     'Large multi-lab replications failed to reproduce many headline effects; p-hacking and low power were exposed.',
     'Publication and citation count are not evidence of truth. A single striking study is a hypothesis, not a fact.'),
    ('Luminiferous Aether', 'Physics', '19th century',
     'Light waves needed a medium ("aether") to travel through, filling all space.',
     'All known waves needed a medium; it was the natural, conservative assumption.',
     'The Michelson-Morley experiment found no aether wind; relativity removed the need for it entirely.',
     'The most "obvious" background assumption can be the thing that has to go. Test the assumption everyone shares.')
ON CONFLICT (name) DO NOTHING;
