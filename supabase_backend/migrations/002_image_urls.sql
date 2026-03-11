-- =============================================================================
-- Digidex — Add image_urls table
-- Run this in the Supabase SQL editor after 001_initial_schema.sql
-- =============================================================================

CREATE TABLE image_urls (
    id   text PRIMARY KEY,   -- image filename, e.g. "Agumon_b.jpg"
    url  text NOT NULL        -- full CDN URL on wikimon.net
);

ALTER TABLE image_urls ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public read" ON image_urls FOR SELECT USING (true);

CREATE INDEX idx_image_urls_id ON image_urls (id);
