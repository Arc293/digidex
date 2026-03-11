"""
scrap_images.py
Fetches image filename → CDN URL mappings from the wikimon MediaWiki API.

Entry point:
    sync_image_urls(digi_obj, existing_url_ids, refresh_all) -> dict[str, str]
        Returns {image_filename: cdn_url} for all images found in digi_obj
        that are not already in existing_url_ids (unless refresh_all=True).
"""

import urllib.parse
import logging
from curl_cffi import requests

logger = logging.getLogger(__name__)

WIKIMON_API_URL = "https://wikimon.net/api.php"
NO_IMG_URL = "https://wikimon.net/images/6/61/Digimon_noimage.jpg"

_SESSION_HEADERS = {
    "User-Agent": "Digidex/1.0 (https://github.com/digidex; scraper bot) python-requests",
    "Accept": "application/json",
}


def _make_session() -> requests.Session:
    s = requests.Session(impersonate="chrome120")
    s.headers.update(_SESSION_HEADERS)
    return s


def _get_image_list(digi_obj: dict, existing_url_ids: set[str], refresh_all: bool) -> list[str]:
    """
    Collect all image filenames referenced in digi_obj that need fetching.
    Returns a list of "Image:<filename>" strings ready for the API.
    """
    image_set = set()
    for digi_data in digi_obj.values():
        for img in digi_data.get("images", []):
            fname = img.split("!")[0]
            if refresh_all or fname not in existing_url_ids:
                image_set.add(f"Image:{fname}")
        for entry in digi_data.get("image_gallery", []):
            fname = entry.get("image", "")
            if fname and (refresh_all or fname not in existing_url_ids):
                image_set.add(f"Image:{fname}")
    return list(image_set)


def _chunks(lst: list, size: int):
    for i in range(0, len(lst), size):
        yield lst[i : i + size]


def sync_image_urls(
    digi_obj: dict,
    existing_url_ids: set[str],
    refresh_all: bool = False,
) -> dict[str, str]:
    """
    Fetches image filename → CDN URL mappings from wikimon for all images in
    digi_obj that are not already tracked (or all, if refresh_all=True).

    Returns a dict {filename: url} of newly fetched / updated entries.
    """
    image_list = _get_image_list(digi_obj, existing_url_ids, refresh_all)
    if not image_list:
        logger.info("No new images to fetch.")
        return {}

    logger.info(f"Fetching URLs for {len(image_list)} images...")
    session = _make_session()
    result: dict[str, str] = {}
    no_img_url = existing_url_ids  # used as fallback key lookup below

    total_chunks = (len(image_list) + 49) // 50
    for i, chunk in enumerate(_chunks(image_list, 50), 1):
        titles = "|".join(urllib.parse.quote(t) for t in chunk)
        params = f"action=query&prop=imageinfo&titles={titles}&iiprop=url&format=json"
        try:
            resp = session.get(url=f"{WIKIMON_API_URL}?{params}", timeout=30)
            if not resp.ok:
                logger.warning(f"Image URL fetch error {resp.status_code} on chunk {i}/{total_chunks}")
                continue
            data = resp.json()
        except Exception:
            logger.exception(f"Failed to fetch image URL chunk {i}/{total_chunks}")
            continue

        pages = data.get("query", {}).get("pages", {})

        # Build normalised-name lookup (API may normalise "Image:foo" → "Image:Foo")
        normalised: dict[str, str] = {}
        for entry in data.get("query", {}).get("normalized", []):
            normalised[entry["to"]] = entry["from"]

        for page in pages.values():
            raw_title = normalised.get(page["title"], page["title"])
            # Strip "Image:" prefix to get the bare filename
            filename = raw_title.split(":", 1)[-1]
            if "imageinfo" in page and page["imageinfo"]:
                url = page["imageinfo"][0]["url"]
            else:
                url = NO_IMG_URL
            result[filename] = url

        logger.info(f"Image URL chunk {i}/{total_chunks} done ({len(result)} total so far)")

    logger.info(f"Image URL sync complete: {len(result)} entries fetched.")
    return result
