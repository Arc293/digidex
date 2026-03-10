-- =============================================================================
-- Digidex — Initial PostgreSQL Schema
-- Run this in the Supabase SQL editor (Dashboard → SQL Editor → New query)
-- =============================================================================

-- ---------------------------------------------------------------------------
-- universe
-- ---------------------------------------------------------------------------
CREATE TABLE universe (
    id          text PRIMARY KEY,
    name        text,
    description text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    last_updated timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- digimon
-- ---------------------------------------------------------------------------
CREATE TABLE digimon (
    id                      text PRIMARY KEY,   -- raw wikimon page title
    name                    text NOT NULL,
    drb_index               float NOT NULL DEFAULT 9999,
    description             text,
    description_japanese    text,
    description_source      text,
    design_and_analysis     text,
    etymology               text,
    images                  text[],
    redirected_names        text[],
    -- Flat arrays for efficient filtering
    search_names            text[],             -- union of all known names (lowercased)
    stat_levels             text[],
    stat_attributes         text[],
    stat_fields             text[],
    stat_type               text[],
    -- Full nested data (JSONB)
    stats                   jsonb,
    debut                   jsonb,
    alt_names               jsonb,
    subspecies              jsonb,
    -- Sync metadata
    last_scraped_revision   text NOT NULL DEFAULT '',
    last_updated            timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- attack_techniques
-- ---------------------------------------------------------------------------
CREATE TABLE attack_techniques (
    id          bigserial PRIMARY KEY,
    digimon_id  text NOT NULL REFERENCES digimon(id) ON DELETE CASCADE,
    name        text,
    translation text,
    kanji       text,
    romaji      text,
    dub_name    text,
    description text
);

-- ---------------------------------------------------------------------------
-- image_gallery
-- ---------------------------------------------------------------------------
CREATE TABLE image_gallery (
    id          bigserial PRIMARY KEY,
    digimon_id  text NOT NULL REFERENCES digimon(id) ON DELETE CASCADE,
    image       text NOT NULL,
    caption     text
);

-- ---------------------------------------------------------------------------
-- evolutions
-- ---------------------------------------------------------------------------
CREATE TABLE evolutions (
    id              bigserial PRIMARY KEY,
    digimon_id      text NOT NULL REFERENCES digimon(id) ON DELETE CASCADE,
    direction       text NOT NULL,      -- 'from' | 'to'
    type            text,               -- 'digimon' | 'non_digimon' | 'any' | 'egg' | 'xros' | 'card' | 'text'
    name            text,
    name_text       text,
    major           boolean NOT NULL DEFAULT false,
    has_fusees      boolean NOT NULL DEFAULT false,
    conditions      text,
    is_special_evo  boolean NOT NULL DEFAULT false,
    special_evo_type text,
    evo_references  text[],
    unknown_param   text[],
    link            text
);

-- ---------------------------------------------------------------------------
-- non_digimon
-- ---------------------------------------------------------------------------
CREATE TABLE non_digimon (
    id                      text PRIMARY KEY,
    name                    text,
    wikitext                text,
    redirected_names        text[],
    last_scraped_revision   text NOT NULL DEFAULT '',
    last_updated            timestamptz NOT NULL DEFAULT now()
);

-- =============================================================================
-- Indexes
-- =============================================================================

-- Ordering
CREATE INDEX idx_digimon_drb_index ON digimon (drb_index);

-- Array-contains queries (GIN for PostgreSQL array operators @>, &&, etc.)
CREATE INDEX idx_digimon_search_names  ON digimon USING GIN (search_names);
CREATE INDEX idx_digimon_stat_levels   ON digimon USING GIN (stat_levels);
CREATE INDEX idx_digimon_stat_attrs    ON digimon USING GIN (stat_attributes);
CREATE INDEX idx_digimon_stat_fields   ON digimon USING GIN (stat_fields);
CREATE INDEX idx_digimon_stat_type     ON digimon USING GIN (stat_type);

-- Subcollection lookups
CREATE INDEX idx_attack_digimon_id   ON attack_techniques (digimon_id);
CREATE INDEX idx_gallery_digimon_id  ON image_gallery (digimon_id);
CREATE INDEX idx_evolutions_digi_dir ON evolutions (digimon_id, direction);
CREATE INDEX idx_evolutions_name     ON evolutions (name);

-- non_digimon ordering
CREATE INDEX idx_non_digimon_name ON non_digimon (name);

-- =============================================================================
-- Row Level Security — public read, no client writes
-- =============================================================================

ALTER TABLE universe          ENABLE ROW LEVEL SECURITY;
ALTER TABLE digimon           ENABLE ROW LEVEL SECURITY;
ALTER TABLE attack_techniques ENABLE ROW LEVEL SECURITY;
ALTER TABLE image_gallery     ENABLE ROW LEVEL SECURITY;
ALTER TABLE evolutions        ENABLE ROW LEVEL SECURITY;
ALTER TABLE non_digimon       ENABLE ROW LEVEL SECURITY;

CREATE POLICY "public read" ON universe          FOR SELECT USING (true);
CREATE POLICY "public read" ON digimon           FOR SELECT USING (true);
CREATE POLICY "public read" ON attack_techniques FOR SELECT USING (true);
CREATE POLICY "public read" ON image_gallery     FOR SELECT USING (true);
CREATE POLICY "public read" ON evolutions        FOR SELECT USING (true);
CREATE POLICY "public read" ON non_digimon       FOR SELECT USING (true);
