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
    ├── requirements.txt
    ├── main.py                  # Sync entry point
    └── wikimon/
        ├── scrap_digimon.py     # wikimon.net scraper
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

### 3. Add GitHub secrets

In your GitHub repo → **Settings → Secrets and variables → Actions**, add:

| Secret | Value |
|--------|-------|
| `SUPABASE_URL` | Your project URL (e.g. `https://xxxx.supabase.co`) |
| `SUPABASE_SERVICE_ROLE_KEY` | Service role key from Supabase dashboard |

### 4. Run the initial sync

Trigger the GitHub Actions workflow manually:
- Go to **Actions → Digimon Sync → Run workflow**
- Check **Re-scrape all pages** for the first run

Or run locally:

```bash
cd supabase_backend/sync
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt

export SUPABASE_URL=https://xxxx.supabase.co
export SUPABASE_SERVICE_ROLE_KEY=your-service-role-key

python main.py --refresh-all    # full sync
python main.py                  # incremental sync
```

---

## Scheduled Sync

The GitHub Actions workflow (`digimon-sync.yml`) runs automatically every day at **4 AM UTC**.
It performs an incremental sync — only pages whose wikimon revision timestamp is newer than
the stored `last_scraped_revision` are re-scraped.

To trigger a full re-scrape manually, run the workflow with **Re-scrape all pages** checked.

---

## Database Schema

```
universe          — sync registry
digimon           — main digimon data (filterable flat columns + JSONB for nested fields)
  ↳ attack_techniques  — attack moves (FK → digimon.id, CASCADE)
  ↳ image_gallery      — images (FK → digimon.id, CASCADE)
  ↳ evolutions         — evolution links (FK → digimon.id, CASCADE)
non_digimon       — non-digimon entities referenced in evolution trees
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
