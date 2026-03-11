# Digidex Supabase Backend

PostgreSQL database (Supabase) + Python sync script for the Digidex website.
Data is scraped from [wikimon.net](https://wikimon.net) and stored in Supabase.
The frontend accesses data directly via the Supabase JS client using the auto-generated PostgREST API.

---

## Project Structure

```
supabase_backend/
├── migrations/
│   └── 001_initial_schema.sql   # Run once in Supabase SQL editor
└── sync/
    ├── .env                     # Local secrets (gitignored — never committed)
    ├── requirements.txt
    ├── main.py                  # Sync entry point
    └── wikimon/
        ├── scrap_digimon.py     # wikimon.net scraper
        ├── scrap_images.py      # image URL scraper
        └── supabase_sync.py     # Supabase read/write helpers
.github/
└── workflows/
    └── digimon-sync.yml         # Scheduled GitHub Actions sync
```

---

## Setup

### 1. Create the Supabase project

1. Go to [https://supabase.com](https://supabase.com) and create a new project
2. Note your **Project URL** and **service role key** (Settings → API)

### 2. Run the migration

In the Supabase dashboard → **SQL Editor** → paste and run `migrations/001_initial_schema.sql`.

This creates all tables, indexes, and RLS policies.

### 3. Configure local secrets

Create `supabase_backend/sync/.env` (gitignored, never committed):

```
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
```

Both values are in the Supabase dashboard under **Settings → API**:
- `SUPABASE_URL` → "Project URL"
- `SUPABASE_SERVICE_ROLE_KEY` → "service_role" key

> The service role key bypasses Row Level Security and is required for the sync
> script to write data. Never use it in frontend code — use the `anon` key there.

### 4. Run the initial sync locally

```bash
cd supabase_backend/sync
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python main.py --refresh-all    # full sync (first run)
python main.py                  # incremental sync
```

The `.env` file is loaded automatically — no need to export environment variables manually.

---

## Scheduled Sync

The GitHub Actions workflow (`digimon-sync.yml`) is configured to run automatically but
requires a **self-hosted runner** because GitHub's hosted runners are blocked by Cloudflare
on wikimon.net.

To register your machine as a self-hosted runner:
- Go to your GitHub repo → **Settings → Actions → Runners → New self-hosted runner**
- Follow the setup instructions for your OS

The workflow performs an incremental sync — only pages whose wikimon revision timestamp is
newer than the stored `last_scraped_revision` are re-scraped.

To trigger manually: **Actions → Digimon Sync → Run workflow**.
Check **Re-scrape all pages** only when you want to force a full re-scrape.

---

## Database Schema

```
universe          — sync registry (last_updated timestamp)
digimon           — main digimon data (filterable flat columns + JSONB for nested fields)
  ↳ attack_techniques  — attack moves (FK → digimon.id, CASCADE)
  ↳ image_gallery      — images (FK → digimon.id, CASCADE)
  ↳ evolutions         — evolution links (FK → digimon.id, CASCADE)
non_digimon       — non-digimon entities referenced in evolution trees (raw wikitext stored)
image_urls        — image filename → CDN URL mappings (scraped from wikimon)
```

---

## Querying Data (Supabase JS client)

```typescript
import { createClient } from '@supabase/supabase-js'
const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY)

// List Digimon ordered by DRB index
const { data } = await supabase
  .from('digimon')
  .select('id, name, drb_index, images')
  .order('drb_index')
  .range(0, 49)

// Filter by level
await supabase.from('digimon').select('*').contains('stat_levels', ['Rookie'])

// Filter by attribute
await supabase.from('digimon').select('*').contains('stat_attributes', ['Vaccine'])

// Multiple filters at once (no Firestore single-array-contains limitation)
await supabase.from('digimon')
  .select('*')
  .contains('stat_levels', ['Rookie'])
  .contains('stat_attributes', ['Vaccine'])
  .order('drb_index')

// Search by name
await supabase.from('digimon').select('*').contains('search_names', ['agumon'])

// Full profile with all subcollections (single query via PostgREST joins)
await supabase.from('digimon')
  .select('*, attack_techniques(*), image_gallery(*), evolutions(*)')
  .eq('id', 'Agumon')
  .single()

// Evolutions only, filtered by direction
await supabase.from('evolutions')
  .select('*')
  .eq('digimon_id', 'Agumon')
  .eq('direction', 'to')
```

---

## Filterable Columns

| Column | Table | Values |
|--------|-------|--------|
| `stat_levels` | `digimon` | e.g. `Rookie`, `Champion`, `Ultimate`, `Mega` |
| `stat_attributes` | `digimon` | e.g. `Vaccine`, `Virus`, `Data` |
| `stat_fields` | `digimon` | e.g. `Nature Spirits`, `Deep Savers` |
| `stat_type` | `digimon` | e.g. `Dragon`, `Reptile` |
| `search_names` | `digimon` | All known names (lowercased) |
| `direction` | `evolutions` | `from` or `to` |
| `type` | `evolutions` | `digimon`, `non_digimon`, `any`, `egg`, `xros`, `card`, `text` |
| `has_fusees` | `evolutions` | boolean |
| `is_special_evo` | `evolutions` | boolean |
