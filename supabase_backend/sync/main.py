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
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from wikimon.supabase_sync import (
    get_all_digimon_revision_dates,
    get_all_image_url_ids,
    upsert_digimon_batch,
    upsert_non_digimon_batch,
    upsert_image_urls,
    delete_digimon,
    ensure_universe,
    touch_universe,
)
from wikimon.scrap_digimon import sync_digimon
from wikimon.scrap_images import sync_image_urls

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

    # Image URLs must be written before digimon batch — image_gallery.image
    # has a FK referencing image_urls.id, so the referenced rows must exist first.
    existing_url_ids = get_all_image_url_ids()
    image_obj = sync_image_urls(digi_obj, existing_url_ids, refresh_all=refresh_all)
    try:
        upsert_image_urls(image_obj)
    except Exception:
        logger.exception("Failed to upsert image URLs")

    try:
        upsert_digimon_batch(digi_obj)
    except Exception:
        logger.exception("Failed to batch upsert digimon")
    updated_count = len(digi_obj)

    try:
        upsert_non_digimon_batch(non_digi_obj)
    except Exception:
        logger.exception("Failed to batch upsert non_digimon")
    non_digi_count = len(non_digi_obj)

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
        "images_fetched": len(image_obj),
        "refresh_all": refresh_all,
    }
    logger.info(f"Sync complete: {summary}")
    return summary


if __name__ == "__main__":
    refresh_all = "--refresh-all" in sys.argv
    _run_sync(refresh_all=refresh_all)
