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

## API Reference (Supabase JS client)

The frontend uses the Supabase JS client, which wraps the auto-generated PostgREST API.
Use the **anon key** in the frontend — it respects RLS (read-only, no writes).

```typescript
import { createClient } from '@supabase/supabase-js'
const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY)
```

---

### Listing Digimon

```typescript
// All Digimon ordered by DRB index, paginated
await supabase
  .from('digimon')
  .select('id, name, drb_index, images')
  .order('drb_index')
  .range(0, 49)           // page 1 (50 per page)
  .range(50, 99)          // page 2
```

**Pagination:** Use `.range(from, to)` — both values are inclusive (0-based).

---

### Filtering

Unlike Firestore, multiple array filters can be combined freely in the same query.

```typescript
// By level
.contains('stat_levels', ['Rookie'])

// By attribute
.contains('stat_attributes', ['Vaccine'])

// By field (Digimon field/group)
.contains('stat_fields', ['Nature Spirits'])

// By type
.contains('stat_type', ['Dragon'])

// By name (search_names is lowercased — always lowercase the search term)
.contains('search_names', ['agumon'])

// Combined — Rookie + Vaccine, ordered by DRB index
await supabase
  .from('digimon')
  .select('id, name, stat_levels, stat_attributes')
  .contains('stat_levels', ['Rookie'])
  .contains('stat_attributes', ['Vaccine'])
  .order('drb_index')
```

**Filterable columns:**

| Column | Type | Example values |
|--------|------|---------------|
| `stat_levels` | `text[]` | `Rookie`, `Champion`, `Ultimate`, `Mega`, `In-Training`, `Fresh` |
| `stat_attributes` | `text[]` | `Vaccine`, `Virus`, `Data`, `Variable`, `Free` |
| `stat_fields` | `text[]` | `Nature Spirits`, `Deep Savers`, `Nightmare Soldiers`, `Wind Guardians`, `Metal Empire`, `Virus Busters`, `Dragon's Roar`, `Jungle Troopers`, `Dark Area`, `Unknown` |
| `stat_type` | `text[]` | `Dragon`, `Reptile`, `Bird`, `Beast`, `Aquatic`, `Insectoid`, `Plant`, `Undead`, etc. |
| `search_names` | `text[]` | All known names for a Digimon (lowercased) — name, romaji, dub names, redirects |

---

### Field selection

Use `.select()` to request only the columns you need — reduces response size significantly.

```typescript
// Only name + images (useful for listing/grid views)
.select('id, name, images, drb_index')

// Only stats
.select('id, name, stats, stat_levels, stat_attributes')

// Everything including child tables (PostgREST join syntax)
.select('*, attack_techniques(*), image_gallery(*), evolutions(*)')
```

---

### Single Digimon — full profile

```typescript
// Full profile with all related data in one query
const { data } = await supabase
  .from('digimon')
  .select('*, attack_techniques(*), image_gallery(*), evolutions(*)')
  .eq('id', 'Agumon')
  .single()

// Minimal — just core fields
await supabase
  .from('digimon')
  .select('id, name, description, images, stats, debut')
  .eq('id', 'Agumon')
  .single()
```

---

### Evolutions

```typescript
// All evolutions for a Digimon
await supabase
  .from('evolutions')
  .select('*')
  .eq('digimon_id', 'Agumon')

// Only digimon it evolves FROM (pre-evolutions)
await supabase
  .from('evolutions')
  .select('*')
  .eq('digimon_id', 'Agumon')
  .eq('direction', 'from')

// Only digimon it evolves TO
await supabase
  .from('evolutions')
  .select('*')
  .eq('digimon_id', 'Agumon')
  .eq('direction', 'to')

// Only major evolutions
.eq('major', true)

// Only special evolutions
.eq('is_special_evo', true)

// Only Xros evolutions (fusees involved)
.eq('has_fusees', true)
```

**Evolution `type` values:** `digimon`, `non_digimon`, `any`, `egg`, `xros`, `card`, `text`

**Evolution `direction` values:** `from` (pre-evolutions), `to` (digivolutions)

---

### Attack Techniques

```typescript
// All attacks for a Digimon
await supabase
  .from('attack_techniques')
  .select('*')
  .eq('digimon_id', 'Agumon')
```

---

### Image Gallery

```typescript
// All gallery images for a Digimon
await supabase
  .from('image_gallery')
  .select('*')
  .eq('digimon_id', 'Agumon')
```

---

### Image URLs

Maps wikimon image filenames (stored in `digimon.images` and `image_gallery.image`) to CDN URLs.

```typescript
// Look up URLs for specific filenames
await supabase
  .from('image_urls')
  .select('id, url')
  .in('id', ['Agumon_b.jpg', 'Agumon_collectors.jpg'])
```

---

### Non-Digimon entities

Non-Digimon entities referenced in evolution trees (items, humans, locations, etc.).

```typescript
// Look up a specific entity
await supabase
  .from('non_digimon')
  .select('id, name, wikitext, redirected_names')
  .eq('id', 'Taichi Yagami')
  .single()

// List all
await supabase
  .from('non_digimon')
  .select('id, name')
  .order('name')
  .range(0, 49)
```
