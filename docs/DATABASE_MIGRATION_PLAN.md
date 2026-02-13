# Database Migration Plan: JSON → Supabase (PostgreSQL)

## Overview

Migrate from scattered JSON files to a local Supabase (PostgreSQL) instance. Develop locally, deploy to Supabase cloud when ready — same workflow as Vercel.

**Current state:** ~40K run files, ~58K ads, 859 brands, 1131 logo entries, 66 schedules — all in JSON files with hand-built cache indexes.

**Target state:** Single PostgreSQL database with proper indexes, queryable via SQL or Supabase client libraries.

## Architecture

```
LOCAL (Phase 1)                         CLOUD (Phase 2)
┌─────────────────────┐                ┌─────────────────────┐
│  supabase start     │                │  Supabase Cloud     │
│  (Docker)           │                │  (hosted Postgres)  │
│                     │   supabase     │                     │
│  PostgreSQL :54322  │ ──db push───▶  │  PostgreSQL         │
│  Studio     :54323  │                │  Studio dashboard   │
│  REST API   :54321  │                │  REST API           │
└────────┬────────────┘                └────────┬────────────┘
         │                                      │
    Flask API :5006                     Flask API (or Edge)
    Scrapers (Python)                   Scrapers (Python)
    Vite frontend :3000                 Deployed frontend
```

## Data Inventory

| Data Source | Current Storage | Records | Notes |
|---|---|---|---|
| Ad results | `output/**/runs/**/*.json` | ~58K ads in ~40K files | Largest dataset; legacy + canonical formats |
| Brand lexicon | `config/brands.json` | 859 brands | Names, synonyms, verified status |
| Brand logos | `output/brand_logos/brand_logo_database.json` | 1131 entries | Logo files stay on disk; DB tracks metadata |
| Schedules | `schedules/*.json` | 66 schedules | Days, times, keywords, enabled |
| Run manifest | `cache/run_manifest.json` | ~40K rows | **Eliminated** — replaced by DB queries |
| Brand index | `cache/brand_index.json` | derived | **Eliminated** — replaced by DB queries |

## Schema Design

### Table: `brands`
The canonical brand lexicon. Replaces `config/brands.json`.

```sql
CREATE TABLE brands (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,          -- canonical display name ("Lay's")
    name_lower  TEXT GENERATED ALWAYS AS (lower(name)) STORED,
    verified    BOOLEAN NOT NULL DEFAULT false,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_brands_name_lower ON brands (name_lower);
```

### Table: `brand_synonyms`
Replaces the `synonyms[]` array in brands.json. Enables fast lookup in either direction.

```sql
CREATE TABLE brand_synonyms (
    id        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    brand_id  BIGINT NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
    synonym   TEXT NOT NULL,
    syn_lower TEXT GENERATED ALWAYS AS (lower(synonym)) STORED,
    UNIQUE (brand_id, syn_lower)
);

CREATE INDEX idx_brand_synonyms_lower ON brand_synonyms (syn_lower);
```

### Table: `brand_logos`
Logo metadata. Replaces `brand_logo_database.json`. Actual image files stay on disk.

```sql
CREATE TABLE brand_logos (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    brand_id      BIGINT NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
    logo_file     TEXT NOT NULL,               -- relative path: "verified/lays.png"
    source        TEXT,                        -- "verified_sync", "scraper", "manual"
    verified      BOOLEAN NOT NULL DEFAULT false,
    verified_at   TIMESTAMPTZ,
    source_url    TEXT,                        -- original URL logo was downloaded from
    md5_hash      TEXT,                        -- content-based dedup
    retailer      TEXT,                        -- which retailer it was first seen on
    first_seen    TIMESTAMPTZ,
    last_seen     TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_brand_logos_brand ON brand_logos (brand_id);
CREATE UNIQUE INDEX idx_brand_logos_md5 ON brand_logos (md5_hash) WHERE md5_hash IS NOT NULL;
```

### Table: `runs`
One row per scrape run. Replaces the run manifest cache.

```sql
CREATE TABLE runs (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    retailer    TEXT NOT NULL,                 -- "kroger", "walmart", "amazon", etc.
    client      TEXT NOT NULL,                 -- "blue_bunny", "proactiv", etc.
    keyword     TEXT,                          -- search term
    run_id      TEXT NOT NULL,                 -- original timestamp ID ("20260212120633")
    timestamp   TIMESTAMPTZ NOT NULL,          -- when the scrape ran
    day         DATE GENERATED ALWAYS AS (timestamp::date) STORED,
    json_path   TEXT,                          -- relative path to source JSON (for reference)
    ad_count    INTEGER NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (retailer, run_id)
);

CREATE INDEX idx_runs_retailer_client ON runs (retailer, client);
CREATE INDEX idx_runs_day ON runs (day);
CREATE INDEX idx_runs_timestamp ON runs (timestamp DESC);
```

### Table: `ads`
Individual ad records. The core table — replaces reading thousands of JSON files.

```sql
CREATE TABLE ads (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id              BIGINT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    original_id         TEXT,                  -- e.g. "amazon::20260212120633::288f3c3d::0"
    module_id           TEXT,                  -- e.g. "amazon::sponsored_brand_video::..."
    ad_type             TEXT NOT NULL,         -- "TOA", "SBA", "Sponsored_Brand", etc.
    ad_subtype          TEXT,                  -- "Video_Single_Product", etc.
    slot                INTEGER,              -- position/index on page

    -- Brand (denormalized for query speed; also linked via ad_brands)
    brand               TEXT,                  -- primary brand name (canonical)
    brand_logo_path     TEXT,                  -- relative path to logo file

    -- Content
    title               TEXT,
    message             TEXT,
    description         TEXT,
    cta                 TEXT,                  -- call-to-action text
    href                TEXT,                  -- destination URL

    -- Media
    image_url           TEXT,                  -- original CDN URL
    image_path          TEXT,                  -- local screenshot path (relative to client dir)
    video_url           TEXT,
    video_path          TEXT,
    product_image_url   TEXT,
    product_title       TEXT,
    product_description TEXT,

    -- Flexible storage for retailer-specific fields
    metadata            JSONB,                -- video_overlay, sbv_structure, etc.

    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_ads_run ON ads (run_id);
CREATE INDEX idx_ads_brand ON ads (brand);
CREATE INDEX idx_ads_type ON ads (ad_type);
CREATE INDEX idx_ads_brand_type ON ads (brand, ad_type);
```

### Table: `ad_brands`
Many-to-many junction for co-branded ads. An ad with `advertisers: ["Herdez", "Jennie-O"]` gets two rows.

```sql
CREATE TABLE ad_brands (
    id        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ad_id     BIGINT NOT NULL REFERENCES ads(id) ON DELETE CASCADE,
    brand_id  BIGINT NOT NULL REFERENCES brands(id) ON DELETE SET NULL,
    UNIQUE (ad_id, brand_id)
);

CREATE INDEX idx_ad_brands_brand ON ad_brands (brand_id);
CREATE INDEX idx_ad_brands_ad ON ad_brands (ad_id);
```

### Table: `schedules`
Replaces `schedules/*.json`.

```sql
CREATE TABLE schedules (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    schedule_id TEXT NOT NULL UNIQUE,          -- "kroger_blue_bunny_ice_cream_7d181867"
    retailer    TEXT NOT NULL,
    client      TEXT NOT NULL,
    keywords    TEXT[] NOT NULL DEFAULT '{}',  -- PostgreSQL array
    days        TEXT[] NOT NULL DEFAULT '{}',  -- ["monday", "wednesday", ...]
    times       TEXT[] NOT NULL DEFAULT '{}',  -- ["08:00", "12:00", ...]
    enabled     BOOLEAN NOT NULL DEFAULT true,
    tz          TEXT DEFAULT '',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_schedules_retailer ON schedules (retailer);
```

### Table: `blacklist`
Brand name verifier blacklist (message-based ad suppression).

```sql
CREATE TABLE blacklist (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    key         TEXT NOT NULL UNIQUE,          -- "MSG:some ad message text"
    reason      TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

## ER Diagram

```
brands ──1:N──▶ brand_synonyms
brands ──1:N──▶ brand_logos
brands ──1:N──▶ ad_brands ◀──N:1── ads
                                      │
runs ──1:N──────────────────────────▶ ads
```

## What Gets Eliminated

Once the DB is populated and the API reads from it:

| File/Cache | Status |
|---|---|
| `cache/run_manifest.json` | **Eliminated** — `SELECT` on `runs` table |
| `cache/brand_index.json` | **Eliminated** — `JOIN` ads + runs + ad_brands |
| `tools/build_run_manifest.py` | **Eliminated** |
| `tools/build_brand_index.py` | **Eliminated** |
| Manifest rebuild in `restart_servers.sh` | **Eliminated** |

JSON files in `output/` are **kept as archival source of truth** — the DB is populated from them and then kept in sync by the scrapers writing to both.

## Migration Phases

### Phase 1: Local Supabase + Schema (this session)
1. Install Supabase CLI
2. `supabase init` in project root
3. Create migration SQL files
4. `supabase start` → local PostgreSQL running

### Phase 2: Populate from existing data
1. Python script reads all JSON files → inserts into DB
2. Brands + synonyms from `config/brands.json`
3. Logos from `brand_logo_database.json`
4. Runs + ads from `output/**/runs/**/*.json`
5. Schedules from `schedules/*.json`

### Phase 3: Flask API reads from DB
1. Add `psycopg2` (or `supabase-py`) to requirements
2. Replace manifest/brand-index queries with SQL
3. Keep JSON fallback during transition

### Phase 4: Scrapers write to DB
1. After each run, insert run + ads into DB
2. Keep writing JSON files as backup/archive
3. Brand additions go to DB instead of (or in addition to) JSON

### Phase 5: Cloud deployment (when ready)
1. Create Supabase cloud project
2. `supabase link --project-ref <id>`
3. `supabase db push` → schema deployed
4. Run population script against cloud DB
5. Update connection string

## Connection Details (Local)

```
Host:     localhost
Port:     54322
Database: postgres
User:     postgres
Password: postgres  (default local dev password)
```

**Connection string:**
```
postgresql://postgres:postgres@localhost:54322/postgres
```

## Query Examples (replacing current code)

### Current: Run manifest count
```python
# Before (Python loops over JSON)
total = 0
for r in mf_runs():
    if retailer and r["retailer"] != retailer: continue
    total += int(r["ad_count"] or 0)
```

### After: SQL
```sql
SELECT SUM(ad_count) as total
FROM runs
WHERE retailer = 'kroger'
  AND day BETWEEN '2025-01-01' AND '2025-12-31';
```

### Current: Brand index lookup
```python
# Before (load brand_index.json, filter in Python)
files = brand_index.get(brand_lower, [])
```

### After: SQL
```sql
SELECT r.json_path, r.ad_count
FROM runs r
JOIN ads a ON a.run_id = r.id
JOIN ad_brands ab ON ab.ad_id = a.id
JOIN brands b ON b.id = ab.brand_id
WHERE b.name_lower = 'yoplait'
  AND r.retailer = 'kroger';
```
