"""
main.py
Standalone sync entry point for the Digidex Supabase backend.

Usage:
  python main.py                 # incremental sync (only changed pages)
  python main.py --refresh-all   # full re-scrape of all pages

Environment variables (required):
  SUPABASE_URL               — your Supabase project URL
  SUPABASE_SERVICE_ROLE_KEY  — service role key (bypasses RLS for writes)
"""

import logging
import sys

from wikimon.supabase_sync import (
    get_all_digimon_revision_dates,
    upsert_digimon,
    upsert_non_digimon,
    delete_digimon,
    ensure_universe,
    touch_universe,
)
from wikimon.scrap_digimon import sync_digimon

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


def _run_sync(refresh_all: bool = False) -> dict:
    ensure_universe(
        "digimon",
        "Digimon",
        "Main Digimon universe — data sourced from wikimon.net",
    )

    existing_revisions = get_all_digimon_revision_dates()

    digi_obj, non_digi_obj, deleted_names = sync_digimon(
        refresh_all=refresh_all,
        existing_revisions=existing_revisions if not refresh_all else {},
        existing_non_digi={},
    )

    updated_count = 0
    for name, data in digi_obj.items():
        revision_date = data.pop("_revision_date", "")
        try:
            upsert_digimon(name, data, revision_date)
            updated_count += 1
        except Exception:
            logger.exception(f"Failed to upsert digimon '{name}'")

    non_digi_count = 0
    for name, entity in non_digi_obj.items():
        try:
            upsert_non_digimon(name, entity)
            non_digi_count += 1
        except Exception:
            logger.exception(f"Failed to upsert non_digimon '{name}'")

    deleted_count = 0
    for name in deleted_names:
        try:
            delete_digimon(name)
            deleted_count += 1
        except Exception:
            logger.exception(f"Failed to delete digimon '{name}'")

    touch_universe("digimon")

    summary = {
        "updated": updated_count,
        "non_digimon_upserted": non_digi_count,
        "deleted": deleted_count,
        "refresh_all": refresh_all,
    }
    logger.info(f"Sync complete: {summary}")
    return summary


if __name__ == "__main__":
    refresh_all = "--refresh-all" in sys.argv
    _run_sync(refresh_all=refresh_all)
