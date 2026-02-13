-- ============================================================
-- Retail Ad Monitor — Initial Schema
-- ============================================================

-- --------------------------------------------------------
-- 1. Brands (canonical brand lexicon)
-- --------------------------------------------------------
CREATE TABLE brands (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    name_lower  TEXT GENERATED ALWAYS AS (lower(name)) STORED,
    verified    BOOLEAN NOT NULL DEFAULT false,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_brands_name_lower ON brands (name_lower);

-- --------------------------------------------------------
-- 2. Brand synonyms
-- --------------------------------------------------------
CREATE TABLE brand_synonyms (
    id        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    brand_id  BIGINT NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
    synonym   TEXT NOT NULL,
    syn_lower TEXT GENERATED ALWAYS AS (lower(synonym)) STORED,
    UNIQUE (brand_id, syn_lower)
);

CREATE INDEX idx_brand_synonyms_lower ON brand_synonyms (syn_lower);

-- --------------------------------------------------------
-- 3. Brand logos (metadata only — files stay on disk)
-- --------------------------------------------------------
CREATE TABLE brand_logos (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    brand_id      BIGINT NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
    logo_file     TEXT NOT NULL,
    source        TEXT,
    verified      BOOLEAN NOT NULL DEFAULT false,
    verified_at   TIMESTAMPTZ,
    source_url    TEXT,
    md5_hash      TEXT,
    retailer      TEXT,
    first_seen    TIMESTAMPTZ,
    last_seen     TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_brand_logos_brand ON brand_logos (brand_id);
CREATE UNIQUE INDEX idx_brand_logos_md5 ON brand_logos (md5_hash) WHERE md5_hash IS NOT NULL;

-- --------------------------------------------------------
-- 4. Scrape runs
-- --------------------------------------------------------
CREATE TABLE runs (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    retailer    TEXT NOT NULL,
    client      TEXT NOT NULL,
    keyword     TEXT,
    run_id      TEXT NOT NULL,
    timestamp   TIMESTAMPTZ NOT NULL,
    day         DATE,  -- populated by trigger on insert/update
    json_path   TEXT,
    ad_count    INTEGER NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (retailer, run_id)
);

CREATE INDEX idx_runs_retailer_client ON runs (retailer, client);
CREATE INDEX idx_runs_day ON runs (day);
CREATE INDEX idx_runs_timestamp ON runs (timestamp DESC);

-- Auto-populate day from timestamp (UTC)
CREATE OR REPLACE FUNCTION set_run_day()
RETURNS TRIGGER AS $$
BEGIN
    NEW.day = (NEW.timestamp AT TIME ZONE 'UTC')::date;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_runs_set_day
    BEFORE INSERT OR UPDATE OF timestamp ON runs
    FOR EACH ROW EXECUTE FUNCTION set_run_day();

-- --------------------------------------------------------
-- 5. Ads (individual ad records)
-- --------------------------------------------------------
CREATE TABLE ads (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id              BIGINT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    original_id         TEXT,
    module_id           TEXT,
    ad_type             TEXT NOT NULL,
    ad_subtype          TEXT,
    slot                INTEGER,

    -- Brand (denormalized for query speed)
    brand               TEXT,
    brand_logo_path     TEXT,

    -- Content
    title               TEXT,
    message             TEXT,
    description         TEXT,
    cta                 TEXT,
    href                TEXT,

    -- Media
    image_url           TEXT,
    image_path          TEXT,
    video_url           TEXT,
    video_path          TEXT,
    product_image_url   TEXT,
    product_title       TEXT,
    product_description TEXT,

    -- Flexible storage for retailer-specific fields
    metadata            JSONB,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_ads_run ON ads (run_id);
CREATE INDEX idx_ads_brand ON ads (brand);
CREATE INDEX idx_ads_type ON ads (ad_type);
CREATE INDEX idx_ads_brand_type ON ads (brand, ad_type);

-- --------------------------------------------------------
-- 6. Ad ↔ Brand junction (co-branded ads)
-- --------------------------------------------------------
CREATE TABLE ad_brands (
    id        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ad_id     BIGINT NOT NULL REFERENCES ads(id) ON DELETE CASCADE,
    brand_id  BIGINT NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
    UNIQUE (ad_id, brand_id)
);

CREATE INDEX idx_ad_brands_brand ON ad_brands (brand_id);
CREATE INDEX idx_ad_brands_ad ON ad_brands (ad_id);

-- --------------------------------------------------------
-- 7. Schedules
-- --------------------------------------------------------
CREATE TABLE schedules (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    schedule_id TEXT NOT NULL UNIQUE,
    retailer    TEXT NOT NULL,
    client      TEXT NOT NULL,
    keywords    TEXT[] NOT NULL DEFAULT '{}',
    days        TEXT[] NOT NULL DEFAULT '{}',
    times       TEXT[] NOT NULL DEFAULT '{}',
    enabled     BOOLEAN NOT NULL DEFAULT true,
    tz          TEXT DEFAULT '',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_schedules_retailer ON schedules (retailer);

-- --------------------------------------------------------
-- 8. Blacklist (ad message suppression)
-- --------------------------------------------------------
CREATE TABLE blacklist (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    key         TEXT NOT NULL UNIQUE,
    reason      TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- --------------------------------------------------------
-- Helper: updated_at trigger
-- --------------------------------------------------------
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_brands_updated_at
    BEFORE UPDATE ON brands
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_brand_logos_updated_at
    BEFORE UPDATE ON brand_logos
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_schedules_updated_at
    BEFORE UPDATE ON schedules
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ── Performance indexes for API queries ──
CREATE INDEX IF NOT EXISTS idx_ads_run_id ON ads(run_id);
CREATE INDEX IF NOT EXISTS idx_ads_brand_lower ON ads(lower(brand));
CREATE INDEX IF NOT EXISTS idx_ads_ad_type ON ads(ad_type);
CREATE INDEX IF NOT EXISTS idx_runs_retailer ON runs(retailer);
CREATE INDEX IF NOT EXISTS idx_runs_keyword_lower ON runs(lower(keyword));
CREATE INDEX IF NOT EXISTS idx_runs_retailer_day ON runs(retailer, day);
