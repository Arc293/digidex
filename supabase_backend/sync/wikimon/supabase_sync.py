"""
supabase_sync.py
Helpers for reading from and writing Digimon/Non-Digimon data to Supabase (PostgreSQL).

Tables:
  digimon
  attack_techniques  (FK → digimon.id, CASCADE DELETE)
  image_gallery      (FK → digimon.id, CASCADE DELETE)
  evolutions         (FK → digimon.id, CASCADE DELETE)
  non_digimon
  universe
"""

import json
import logging
import os
from datetime import datetime, timezone

from supabase import create_client, Client

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Supabase client (lazy singleton)
# ---------------------------------------------------------------------------

_client: Client | None = None


def get_db() -> Client:
    global _client
    if _client is None:
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
        _client = create_client(url, key)
    return _client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------

def _fetch_all_rows(table: str, columns: str) -> list[dict]:
    """Paginate through all rows of a table, bypassing the default 1000-row limit."""
    db = get_db()
    result = []
    page_size = 1000
    offset = 0
    while True:
        rows = (
            db.table(table)
            .select(columns)
            .range(offset, offset + page_size - 1)
            .execute()
            .data
        )
        result.extend(rows)
        if len(rows) < page_size:
            break
        offset += page_size
    return result


def get_all_digimon_revision_dates() -> dict[str, str]:
    """
    Returns {digimon_name: last_scraped_revision} for all rows in digimon.
    Used to detect which pages need re-scraping.
    """
    rows = _fetch_all_rows("digimon", "id, last_scraped_revision")
    return {row["id"]: row.get("last_scraped_revision", "") for row in rows}


def get_all_non_digimon_keys() -> set[str]:
    """Returns the set of all non_digimon IDs (page titles)."""
    rows = _fetch_all_rows("non_digimon", "id")
    return {row["id"] for row in rows}


# ---------------------------------------------------------------------------
# Build helpers
# ---------------------------------------------------------------------------

def _build_digimon_row(digi_data: dict, revision_date: str) -> dict:
    """
    Transforms a scraped digimon dict into a flat PostgreSQL row.
    Mirrors the logic of firestore_sync._build_digimon_main_doc().
    """
    stats_raw = digi_data.get("stats", {})

    # Flat filterable arrays
    stat_levels     = [s["value"] for s in stats_raw.get("levels", [])]
    stat_attributes = [s["value"] for s in stats_raw.get("attributes", [])]
    stat_fields     = [s["value"] for s in stats_raw.get("fields", [])]
    stat_type       = [s["value"] for s in stats_raw.get("type", [])]

    # Full stats JSONB (includes references + flat arrays for convenience)
    stats_jsonb = {
        "levels":           stat_levels,
        "attributes":       stat_attributes,
        "fields":           stat_fields,
        "groups":           [s["value"] for s in stats_raw.get("groups", [])],
        "type":             stat_type,
        "weight":           [s["value"] for s in stats_raw.get("weight", [])],
        "class_type":       stats_raw.get("class_type", {}),
        "equipment":        stats_raw.get("equipment", []),
        "levels_full":      stats_raw.get("levels", []),
        "attributes_full":  stats_raw.get("attributes", []),
        "fields_full":      stats_raw.get("fields", []),
        "type_full":        stats_raw.get("type", []),
        "weight_full":      stats_raw.get("weight", []),
    }

    # Build flat search_names (all known names, deduplicated)
    alt = digi_data.get("alt_names", {})
    search_names = list({
        digi_data.get("name", ""),
        alt.get("romaji", ""),
        alt.get("development_name", ""),
        *alt.get("kanji", []),
        *[d["value"] for d in alt.get("dub_names", []) if d.get("value")],
        *(
            [alt["other_names"]["value"]]
            if isinstance(alt.get("other_names"), dict) and alt["other_names"].get("value")
            else []
        ),
        *digi_data.get("redirected_names", []),
    } - {""})

    return {
        "id":                   digi_data.get("name", ""),   # overridden by caller with page title
        "name":                 digi_data.get("name", ""),
        "drb_index":            digi_data.get("drb_index", 9999),
        "description":          digi_data.get("description", ""),
        "description_japanese": digi_data.get("description_japanese", ""),
        "description_source":   digi_data.get("description_source", ""),
        "design_and_analysis":  digi_data.get("design_and_analysis", ""),
        "etymology":            digi_data.get("etymology", ""),
        "images":               digi_data.get("images", []),
        "redirected_names":     digi_data.get("redirected_names", []),
        "search_names":         search_names,
        "stat_levels":          stat_levels,
        "stat_attributes":      stat_attributes,
        "stat_fields":          stat_fields,
        "stat_type":            stat_type,
        "stats":                stats_jsonb,
        "debut":                digi_data.get("debut", {}),
        "alt_names":            alt,
        "subspecies":           digi_data.get("subspecies", []),
        "last_scraped_revision": revision_date,
        "last_updated":         _now(),
    }


# ---------------------------------------------------------------------------
# Write helpers — Digimon
# ---------------------------------------------------------------------------

_BATCH_SIZE = 500


def upsert_digimon_batch(digi_obj: dict) -> None:
    """
    Batch upsert all digimon and their child records.
    digi_obj: {name: data} where data may contain '_revision_date'.

    Reduces API calls from ~7 per digimon to ~7 total regardless of count.
    """
    if not digi_obj:
        return
    db = get_db()
    names = list(digi_obj.keys())

    # 1. Build and batch-upsert main digimon rows
    main_rows = []
    for name, data in digi_obj.items():
        revision_date = data.pop("_revision_date", "")
        row = _build_digimon_row(data, revision_date)
        row["id"] = name
        main_rows.append(row)

    for i in range(0, len(main_rows), _BATCH_SIZE):
        db.table("digimon").upsert(main_rows[i : i + _BATCH_SIZE]).execute()

    # 2. Delete all child records for these digimon in bulk
    for i in range(0, len(names), _BATCH_SIZE):
        batch = names[i : i + _BATCH_SIZE]
        db.table("attack_techniques").delete().in_("digimon_id", batch).execute()
        db.table("image_gallery").delete().in_("digimon_id", batch).execute()
        db.table("evolutions").delete().in_("digimon_id", batch).execute()

    # 3. Collect and batch-insert all child records
    all_techs, all_gallery, all_evos = [], [], []

    for name, data in digi_obj.items():
        for t in data.get("attack_techniques", []):
            all_techs.append({
                "digimon_id":  name,
                "name":        t.get("name", ""),
                "translation": t.get("translation", ""),
                "kanji":       t.get("kanji", ""),
                "romaji":      t.get("romaji", ""),
                "dub_name":    t.get("dub_name", ""),
                "description": t.get("description", ""),
            })
        for g in data.get("image_gallery", []):
            all_gallery.append({
                "digimon_id": name,
                "image":      g.get("image", ""),
                "caption":    g.get("caption", ""),
            })
        for evo in data.get("evolve_from", []):
            all_evos.append({**_build_evo_row(evo), "digimon_id": name, "direction": "from"})
        for evo in data.get("evolve_to", []):
            all_evos.append({**_build_evo_row(evo), "digimon_id": name, "direction": "to"})

    for i in range(0, len(all_techs), _BATCH_SIZE):
        db.table("attack_techniques").insert(all_techs[i : i + _BATCH_SIZE]).execute()
    for i in range(0, len(all_gallery), _BATCH_SIZE):
        db.table("image_gallery").insert(all_gallery[i : i + _BATCH_SIZE]).execute()
    for i in range(0, len(all_evos), _BATCH_SIZE):
        db.table("evolutions").insert(all_evos[i : i + _BATCH_SIZE]).execute()

    logger.info(f"Batch upserted {len(names)} digimon.")


def _build_evo_row(evo: dict) -> dict:
    return {
        "type":             evo.get("type", ""),
        "name":             evo.get("name", ""),
        "name_text":        evo.get("name_text", ""),
        "major":            bool(evo.get("major", False)),
        "has_fusees":       bool(evo.get("has_fusees", False)),
        "conditions":       evo.get("conditions", ""),
        "is_special_evo":   bool(evo.get("is_special_evo", False)),
        "special_evo_type": evo.get("special_evo_type", ""),
        "evo_references":   evo.get("references", []),
        "unknown_param":    evo.get("unknown_param", []),
        "link":             evo.get("link", ""),
    }


def delete_digimon(name: str) -> None:
    """
    Delete a digimon row — CASCADE constraints handle child table rows.
    """
    db = get_db()
    db.table("digimon").delete().eq("id", name).execute()
    logger.info(f"Deleted digimon: {name}")


# ---------------------------------------------------------------------------
# Write helpers — Non-Digimon
# ---------------------------------------------------------------------------

def upsert_non_digimon_batch(non_digi_obj: dict) -> None:
    """Batch upsert all non_digimon rows in one (or a few) API calls."""
    if not non_digi_obj:
        return
    db = get_db()
    rows = [
        {
            "id":                   name,
            "name":                 name,
            "wikitext":             entity.get("wikitext", ""),
            "redirected_names":     entity.get("redirected_names", []),
            "last_scraped_revision": entity.get("_revision_date", ""),
            "last_updated":         _now(),
        }
        for name, entity in non_digi_obj.items()
    ]
    for i in range(0, len(rows), _BATCH_SIZE):
        db.table("non_digimon").upsert(rows[i : i + _BATCH_SIZE]).execute()
    logger.info(f"Batch upserted {len(rows)} non_digimon.")


# ---------------------------------------------------------------------------
# Write helpers — Universe registry
# ---------------------------------------------------------------------------

def ensure_universe(universe_id: str, name: str, description: str = "") -> None:
    """Creates the universe row if it does not exist."""
    db = get_db()
    existing = db.table("universe").select("id").eq("id", universe_id).execute().data
    if not existing:
        db.table("universe").insert({
            "id":          universe_id,
            "name":        name,
            "description": description,
            "created_at":  _now(),
            "last_updated": _now(),
        }).execute()
        logger.info(f"Created universe: {universe_id}")


def touch_universe(universe_id: str) -> None:
    """Update last_updated on a universe row."""
    db = get_db()
    db.table("universe").update({"last_updated": _now()}).eq("id", universe_id).execute()


# ---------------------------------------------------------------------------
# Write helpers — Image URLs
# ---------------------------------------------------------------------------

def get_all_image_url_ids() -> set[str]:
    """Returns the set of all image filenames already stored in image_urls."""
    rows = _fetch_all_rows("image_urls", "id")
    return {row["id"] for row in rows}


def get_missing_image_filenames() -> set[str]:
    """
    Returns image filenames referenced in image_gallery or digimon.images
    that have no entry in image_urls yet.

    Used to backfill gaps left by partial or incremental syncs.
    """
    existing = get_all_image_url_ids()

    # Filenames from image_gallery (already flat — one filename per row)
    gallery_rows = _fetch_all_rows("image_gallery", "image")
    referenced = {row["image"] for row in gallery_rows if row.get("image")}

    # Filenames from digimon.images (text[] column — flatten the arrays)
    digimon_rows = _fetch_all_rows("digimon", "images")
    for row in digimon_rows:
        for img in row.get("images") or []:
            fname = img.split("!")[0]   # strip thumbnail suffix if present
            if fname:
                referenced.add(fname)

    return referenced - existing


def upsert_image_urls(image_obj: dict[str, str]) -> None:
    """
    Upsert {filename: url} entries into the image_urls table.
    Operates in batches of 500 to stay within Supabase request limits.
    """
    if not image_obj:
        return
    db = get_db()
    rows = [{"id": fname, "url": url} for fname, url in image_obj.items()]
    for i in range(0, len(rows), _BATCH_SIZE):
        db.table("image_urls").upsert(rows[i : i + _BATCH_SIZE]).execute()
    logger.info(f"Upserted {len(rows)} image URL entries.")
