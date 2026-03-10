"""
scrap_digimon.py
Adapted wikimon scraper for Cloud Functions — no local file I/O.

All data is fetched from the wikimon MediaWiki API, parsed in-memory, and
returned as plain Python dicts ready for Firestore.
"""

import re
import urllib.parse
import logging
from curl_cffi import requests
import wikitextparser as wtp
import unicodedata
from datetime import datetime
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

WIKIMON_API_URL = "https://wikimon.net/api.php"
_SESSION_HEADERS = {
    "User-Agent": "Digidex/1.0 (https://github.com/digidex; scraper bot) python-requests",
    "Accept": "application/json",
}


def _api_get(session: requests.Session, params: str, timeout: int = 30) -> dict:
    """
    GET the wikimon API with the given pre-encoded query string.
    Raises RuntimeError with the raw response text if JSON decoding fails.
    """
    resp = session.get(url=WIKIMON_API_URL, params=params, timeout=timeout)
    if not resp.ok:
        raise RuntimeError(f"wikimon API error {resp.status_code}: {resp.text[:500]}")
    text = resp.text
    if not text.strip():
        raise RuntimeError(
            f"wikimon API returned an empty response for params: {params}"
        )
    try:
        return resp.json()
    except Exception:
        raise RuntimeError(
            f"wikimon API returned non-JSON (status {resp.status_code}): {text[:500]}"
        )


# ---------------------------------------------------------------------------
# Wikimon API helpers
# ---------------------------------------------------------------------------

def _get_digimon_list_for_api(value_list: list[str]) -> list[str]:
    """Split a list of digimon names into URL-encoded pipe-separated chunks of 50."""
    chunks = []
    chunk = []
    for name in value_list:
        chunk.append(urllib.parse.quote(name))
        if len(chunk) == 50:
            chunks.append("|".join(chunk))
            chunk.clear()
    if chunk:
        chunks.append("|".join(chunk))
    return chunks


def _make_session() -> requests.Session:
    s = requests.Session(impersonate="chrome120")
    s.headers.update(_SESSION_HEADERS)
    return s


def get_digimon_list(session: requests.Session | None = None) -> list[str]:
    """
    Fetch all Digimon page titles from wikimon category members.
    Returns a flat list of page titles.
    """
    if session is None:
        session = _make_session()

    digimon_list = []

    # Category: Digimon (pageid=6)
    params = "action=query&format=json&list=categorymembers&cmpageid=6&cmlimit=500"
    continue_param = ""
    while True:
        resp = _api_get(session, params + continue_param)
        digimon_list.extend([
            d["title"] for d in resp["query"]["categorymembers"]
            if d["pageid"] not in (565, 58049, 5, 641, 38872)
            and not d["title"].startswith("Category:")
        ])
        if "continue" in resp:
            continue_param = f'&cmcontinue={resp["continue"]["cmcontinue"]}'
        else:
            break

    # Category: Unreleased Digimon (pageid=686)
    params = "action=query&cmprop=title&format=json&list=categorymembers&cmpageid=686&cmlimit=500"
    continue_param = ""
    while True:
        resp = _api_get(session, params + continue_param)
        digimon_list.extend([d["title"] for d in resp["query"]["categorymembers"]])
        if "continue" in resp:
            continue_param = f'&cmcontinue={resp["continue"]["cmcontinue"]}'
        else:
            break

    return digimon_list


def get_revision_timestamps(
    digimon_list: list[str],
    session: requests.Session,
) -> dict[str, str]:
    """
    Returns {page_title: revision_timestamp} for all pages in digimon_list.
    """
    result = {}
    for titles in _get_digimon_list_for_api(digimon_list):
        params = f"action=query&prop=revisions&titles={titles}&rvslots=*&rvprop=timestamp&format=json"
        data = _api_get(session, params)
        for _, body in data["query"]["pages"].items():
            result[body["title"]] = body["revisions"][0]["timestamp"]
    return result


def get_page_wikitexts(
    title_list: list[str],
    session: requests.Session,
) -> dict[str, dict]:
    """
    Fetches raw wikitext for each page title.
    Returns {page_title: {"wikitext": str, "redirected_names": []}}.
    """
    result = {}
    chunks = list(_get_digimon_list_for_api(title_list))
    total = len(chunks)
    for i, titles in enumerate(chunks, start=1):
        logger.info(f"Fetching wikitext chunk {i}/{total} ({len(result)} pages so far)...")
        params = f"action=query&prop=revisions&titles={titles}&rvslots=*&rvprop=content&format=json"
        data = _api_get(session, params)
        for _, body in data["query"]["pages"].items():
            title = body["title"]
            if "revisions" in body:
                result[title] = {
                    "wikitext": body["revisions"][0]["slots"]["main"]["*"],
                    "redirected_names": [],
                }
    return result


def resolve_redirects(
    session: requests.Session,
    page_content: dict[str, dict],
) -> tuple[dict[str, dict], bool]:
    """
    For any pages whose wikitext starts with #REDIRECT, fetch the target page's
    wikitext and store it under the original key. Also populates 'redirected_names'.
    Returns (updated_content, changed_flag).
    """
    redirected = []
    original_names: dict[str, list[str]] = {}
    changed = False

    for title, body in page_content.items():
        if "redirected_names" not in body:
            body["redirected_names"] = []
        wikitext = body.get("wikitext", "")
        if wikitext.strip().lower().startswith("#redirect"):
            match = re.search(r"\[\[(.*?)\]\]", wikitext)
            if match:
                target = match.group(1)
                redirected.append(target)
                original_names.setdefault(target, []).append(title)
                if target not in body["redirected_names"]:
                    body["redirected_names"].append(target)
                    changed = True

    if not redirected:
        return page_content, changed

    for titles in _get_digimon_list_for_api(redirected):
        params = f"action=query&prop=revisions&titles={titles}&rvslots=*&rvprop=content&format=json"
        data = _api_get(session, params)
        for _, body in data["query"]["pages"].items():
            if "revisions" not in body:
                continue
            wikitext = body["revisions"][0]["slots"]["main"]["*"]
            for orig_title in original_names.get(body["title"], []):
                page_content[orig_title]["wikitext"] = wikitext
                changed = True

    return page_content, changed


# ---------------------------------------------------------------------------
# Parsing utilities (ported from original scraper)
# ---------------------------------------------------------------------------

def _get_date(date_string: str) -> datetime:
    return datetime.fromisoformat(date_string)


def _get_info_template(wikitext: str) -> wtp.Template | None:
    parsed = wtp.parse(wikitext)
    return next((t for t in parsed.templates if t.name.strip() == "S2"), None)


def _remove_refs(content: str) -> str:
    soup = BeautifulSoup(content, "lxml")
    for ref in soup.find_all("ref"):
        ref.decompose()
    return soup.text


def _replace_breaks(content: str) -> str:
    return content.replace("<br>", "\n").replace("<br/>", "\n")


def _get_tag_property(tag: str, prop: str, text: str) -> str:
    soup = BeautifulSoup(text, "lxml")
    tg = soup.find(tag)
    if not tg or not tg.has_attr(prop):
        return ""
    val = tg[prop]
    return val[:-1] if val.endswith("/") else val


def _replace_ref_tag_with_template(content: str) -> str:
    soup = BeautifulSoup(content, "lxml")
    for ref in soup.find_all("ref"):
        ref_text = []
        if ref.string and ref.string.startswith("[["):
            ref_text.append(ref.string)
        elif ref.has_attr("name"):
            val = ref["name"]
            if val.endswith("/"):
                val = val[:-1]
            ref_text.append(val)
        ref.replace_with("{{ref|" + "|".join(ref_text) + "}}")
    return soup.text


def _template_replacer(template: wtp.Template) -> str:
    match template.name.lower():
        case "fc":
            return template.arguments[0].value
        case "w" | "wikt" | "ety":
            if len(template.arguments) == 1:
                return f'"{template.arguments[0].value}"'
            return _first_non_named_arg(template.arguments[1:])
        case "at" | "ato" | "eq" | "eqo":
            if len(template.arguments) == 1:
                return template.arguments[0].value
            filtered = _get_all_non_named_arg(template.arguments)
            return filtered[0] + " " + " ".join(f"({v})" for v in filtered[1:])
        case "br":
            return "\n"
        case "etyk" | "j" | "wikia" | "j2" | "url2":
            if len(template.arguments) == 1:
                return template.arguments[0].value
            return f"{template.arguments[1].value} ({template.arguments[0].value})"
        case "fm" | "fmo" | "nn" | "nno" | "fgm":
            if len(template.arguments) == 1:
                return template.arguments[0].value
            return _first_non_named_arg(template.arguments)
        case "noprofile":
            if len(template.arguments) == 1:
                return f'No official description. Fanmade description:\n"{template.arguments[0].value}"'
            return "No description found."
        case "note" | "s2ep":
            return ""
        case "untranslated":
            return "No English description found"
        case "xab":
            return f'\nThe effect on {"/".join(t.value for t in template.arguments)}\'s Digicore due to the X-Antibody\n'
        case "dd":
            return " (Digimon Reference Book) "
        case "dl":
            return "Digimon Life"
        case "ref":
            return wtp.parse(template.arguments[0].value).plain_text().strip()
        case "rfc":
            return f"Card: {template.arguments[0].value}-{template.arguments[1].value}"
        case "rfe":
            return f"Episode: {template.arguments[0].value}-{template.arguments[1].value} ({template.arguments[2].value})"
        case "refd":
            name_val = template.arguments[1].value if len(template.arguments) > 1 else template.arguments[0].value.replace(" ", "").lower()
            return f"{template.arguments[0].value} (https://digimon.net/reference/detail.php?directory_name={name_val})"
        case "dcdapmhl":
            return f"[{template.arguments[0].value.strip().upper()}]"
        case "eng":
            return "{English}"
        case "jp":
            return "{Japanese}"
        case _:
            if template.arguments:
                return template.arguments[0].value
            return template.name


def _template_replacer_refs(template: wtp.Template) -> str:
    match template.name.lower():
        case "ref":
            return f" ({wtp.parse(template.arguments[0].value).plain_text().strip()})"
        case "rfc":
            return f" (Card: {template.arguments[0].value}-{template.arguments[1].value})"
        case "rfe":
            return f" (Episode: {template.arguments[0].value}-{template.arguments[1].value} ({template.arguments[2].value}))"
        case "refd":
            return f" ({template.arguments[0].value} (https://digimon.net/reference/detail.php?directory_name={template.arguments[1].value}))"
        case "note":
            return f"Note: {template.arguments[0].value}"
        case _:
            if template.arguments:
                return template.arguments[0].value
            return template.name


def _recursive_parse_template(content: str, delete_wikilinks: bool = False) -> str:
    parsed = wtp.parse(content)
    if delete_wikilinks:
        for link in parsed.wikilinks:
            del link.target
    while parsed.templates or parsed.wikilinks:
        content = parsed.plain_text(replace_templates=_template_replacer)
        parsed = wtp.parse(content)
    return content.strip()


def _get_arg_name(prefix: str, count: int | str) -> str:
    if count == 0:
        return prefix
    return prefix + str(count)


def _first_non_named_arg(arguments: list) -> str:
    for a in arguments:
        if a.name.isdigit():
            return a.value
    return ""


def _get_all_non_named_arg(arguments: list) -> list[str]:
    return [a.value for a in arguments if a.name.isdigit()]


def _scrap_stat_with_prefix(
    info_template: wtp.Template,
    prefix: str,
    count: int,
    delete_wikilinks: bool = False,
) -> list[dict]:
    stat_list = []
    if not info_template.has_arg(_get_arg_name(prefix, count)):
        count = "l"
    while info_template.has_arg(_get_arg_name(prefix, count)):
        obj: dict = {}
        base_arg = info_template.get_arg(_get_arg_name(prefix, count))
        if count == "l" and not base_arg.value.strip():
            break
        if not base_arg.value.strip():
            count = count + 1 if count != 0 else count + 2
            continue
        obj["value"] = unicodedata.normalize(
            "NFKC",
            _recursive_parse_template(_replace_breaks(base_arg.value.strip()), delete_wikilinks),
        )
        # Resolve reference argument
        ref_arg = None
        if prefix == "dub":
            ref_arg = info_template.get_arg("dref" + (str(count) if count > 0 else ""))
        elif prefix == "yd":
            ref_arg = info_template.get_arg("ydr")
        elif prefix == "wp":
            suffix = str(count) if count > 0 else ""
            if info_template.has_arg("wpd" + suffix):
                ref_arg = info_template.get_arg("wpd" + suffix)
            else:
                ref_arg = info_template.get_arg("wp" + suffix + "d")
        else:
            ref_arg = info_template.get_arg(_get_arg_name(prefix, count) + "ref")

        has_ref = False
        if ref_arg:
            ref_templates = wtp.parse(ref_arg.value).templates
            if ref_templates:
                obj["reference"] = _recursive_parse_template(_replace_breaks(ref_templates[0].string))
                has_ref = True
            else:
                ref1 = _get_tag_property("ref", "name", ref_arg.value)
                ref2 = wtp.parse(ref_arg.value).plain_text().strip()
                ref_name = ref1 + (f" ({ref2})" if ref2 else "") if ref1 else ref2
                if ref_name:
                    obj["reference"] = _replace_breaks(ref_name)
                    has_ref = True
        if not has_ref:
            obj["reference"] = ""

        stat_list.append(obj)

        if count == "l":
            break
        count = count + 1 if count > 0 else count + 2
        if not info_template.has_arg(_get_arg_name(prefix, count)):
            count = "l"

    return stat_list


def _scrap_digimoji(info_template: wtp.Template) -> dict:
    digimoji = {}
    for da_key in ("da", "da2"):
        if info_template.has_arg(da_key):
            da = info_template.get_arg(da_key)
            templates = wtp.parse(da.value).templates
            if templates:
                t = templates[0]
                digimoji[t.name] = [a.value.strip() for a in t.arguments]
    return digimoji


# ---------------------------------------------------------------------------
# Per-digimon scraping functions
# ---------------------------------------------------------------------------

def scrap_descriptions(digimon: str, wikitext: str, digi_obj: dict) -> bool:
    """Parse the description fields from the S2 infobox template."""
    info = _get_info_template(wikitext)
    if not info:
        return False

    found = False
    for arg in info.arguments:
        if "pe" in arg.name or arg.name == "e":
            desc = _replace_breaks(_remove_refs(arg.value))
            digi_obj.setdefault(digimon, {})
            digi_obj[digimon]["description"] = _recursive_parse_template(desc)
            found = True
            jap_desc = ""
            if arg.name == "e":
                if info.has_arg("un"):
                    digi_obj[digimon]["description_source"] = info.get_arg("un").value.strip()
                elif info.has_arg("p"):
                    digi_obj[digimon]["description_source"] = info.get_arg("p").value.strip()
                if info.has_arg("j"):
                    jap_desc = info.get_arg("j").value
            else:
                source_name = arg.name.replace("e", "n")
                jap_name = arg.name.replace("e", "j")
                if info.has_arg(source_name):
                    if "1a" in source_name:
                        source_name = arg.name.replace("e", "un")
                    digi_obj[digimon]["description_source"] = info.get_arg(source_name).value.strip()
                if info.has_arg(jap_name):
                    jap_desc = info.get_arg(jap_name).value
            if jap_desc:
                digi_obj[digimon]["description_japanese"] = _recursive_parse_template(
                    _replace_breaks(_remove_refs(jap_desc))
                )
            break

    if not found:
        logger.warning(f"Description not found for {digimon}")
    return found


def scrap_stats(digimon: str, wikitext: str, digi_obj: dict) -> None:
    """Parse all infobox stats and alt-names from the S2 template."""
    info = _get_info_template(wikitext)
    if not info:
        return

    attributes = _scrap_stat_with_prefix(info, "a", 1)
    class_type_list = _scrap_stat_with_prefix(info, "c", 0)
    class_type = class_type_list[0] if class_type_list else {}
    fields = _scrap_stat_with_prefix(info, "f", 1)
    groups = _scrap_stat_with_prefix(info, "g", 1)
    levels = _scrap_stat_with_prefix(info, "l", 1)
    type_ = _scrap_stat_with_prefix(info, "t", 1)
    weight = _scrap_stat_with_prefix(info, "w", 0)
    equipment = _scrap_stat_with_prefix(info, "wp", 0)

    stats = {
        "attributes": attributes,
        "class_type": class_type,
        "fields": fields,
        "groups": groups,
        "levels": levels,
        "type": type_,
        "weight": weight,
        "equipment": equipment,
    }

    def _single(prefix):
        lst = _scrap_stat_with_prefix(info, prefix, 0)
        return lst[0]["value"] if lst else ""

    def _single_obj(prefix):
        lst = _scrap_stat_with_prefix(info, prefix, 0)
        return lst[0] if lst else {}

    debut = {
        "anime_debut": _single("ad"),
        "card_debut": _single("cd"),
        "game_debut": _single("gd"),
        "manga_debut": _single("md"),
        "vpet_debut": _single("vd"),
        "debut_year": _single_obj("yd"),
        "drb_entry_date": {
            "date": _single("drbed"),
            "year": _single("drbedy"),
        },
    }

    titles = _scrap_stat_with_prefix(info, "aln", 1)
    other_names = _single_obj("altn")
    dub_names = _scrap_stat_with_prefix(info, "dub", 0)
    digimoji = _scrap_digimoji(info)
    development_name = _single("develn")
    kanji = [k["value"] for k in _scrap_stat_with_prefix(info, "kan", 0)]
    ol = _scrap_stat_with_prefix(info, "ol", 0)
    other_language = _replace_breaks(ol[0]["value"] if ol else "")
    romaji = _single("rom")

    alt_names = {
        "titles": titles,
        "other_names": other_names,
        "dub_names": dub_names,
        "digimoji": digimoji,
        "development_name": development_name,
        "kanji": kanji,
        "other_language": other_language,
        "romaji": romaji,
    }

    design_and_analysis = _single("dsgn")
    images = [img["value"].split("!")[0] for img in _scrap_stat_with_prefix(info, "image", 0)]
    subspecies = _scrap_stat_with_prefix(info, "s", 1)
    name_list = _scrap_stat_with_prefix(info, "name", 0)
    name = name_list[0]["value"] if name_list else digimon
    etymology = _single("ety")

    digi_obj.setdefault(digimon, {}).update({
        "name": name,
        "images": images,
        "stats": stats,
        "debut": debut,
        "alt_names": alt_names,
        "subspecies": subspecies,
        "design_and_analysis": design_and_analysis,
        "etymology": etymology,
    })


def scrap_drb_index(page_content: dict, digi_obj: dict) -> None:
    """Assign DRB index numbers to each digimon in digi_obj."""
    index_map: dict[str, float] = {}
    old_digimon: list[str] = []
    link_digi: dict[str, str] = {}
    digi_with_index: set[str] = set()

    def _extract_numbers(num_list: list[str], digimon: str) -> list[int]:
        nums = []
        for s in num_list:
            if s.isdigit():
                nums.append(int(s))
            else:
                for part in s.split(","):
                    a = part.strip().rstrip("thstndrd")
                    if a.isdigit():
                        nums.append(int(a))
        return nums

    def _extract_digimon_from_drbentry(template: wtp.Template) -> list[str]:
        count = 2
        result = []
        while template.has_arg(str(count) + "a"):
            raw = template.get_arg(str(count) + "a").value
            if " and " in raw:
                result.extend(d.strip() for d in raw.split(" and ") if d.strip())
            else:
                result.extend(d.strip() for d in raw.split(",") if d.strip())
            count += 1
        return result

    for digimon, body in page_content.items():
        wikitext = body.get("wikitext", "")
        info = _get_info_template(wikitext)
        if not info or not info.has_arg("drbentry"):
            continue
        raw_val = info.get_arg("drbentry").value
        drb_templates = wtp.parse(raw_val).templates
        if drb_templates:
            drb_t = drb_templates[0]
            if drb_t.name == "DRBEntry":
                if drb_t.arguments:
                    nums = _extract_numbers(_get_all_non_named_arg(drb_t.arguments), digimon)
                    digis = _extract_digimon_from_drbentry(drb_t)
                    digis.append(digimon)
                    nums.sort()
                    digis.sort()
                    if len(nums) == len(digis):
                        for i, d in enumerate(digis):
                            if d in digi_obj:
                                index_map[d] = nums[i]
                                digi_with_index.add(d)
                else:
                    old_digimon.append(digimon)
                    digi_with_index.add(digimon)
        else:
            if "incorporated into" in raw_val:
                match = re.search(r"incorporated into (.*?)\'s profile", raw_val)
                if match:
                    target = match.group(1)
                    link_digi[digimon] = target
                    digi_with_index.add(digimon)

    old_digimon.sort()
    for i, d in enumerate(old_digimon):
        index_map[d] = i + 1

    for orig, target in link_digi.items():
        if target in index_map:
            index_map[orig] = index_map[target] + 0.1

    for digimon, idx in index_map.items():
        if digimon in digi_obj:
            digi_obj[digimon]["drb_index"] = idx


def scrap_attack_techs(digimon: str, wikitext: str, digi_obj: dict) -> bool:
    """Parse attack techniques from the T template."""
    parsed = wtp.parse(wikitext)
    tech_template = next(
        (t for t in parsed.templates if t.name and t.name.strip() == "T"), None
    )
    if not tech_template:
        return False

    names = [_remove_refs(x["value"]) for x in _scrap_stat_with_prefix(tech_template, "name", 0, True)]
    translations = [_remove_refs(x["value"]) for x in _scrap_stat_with_prefix(tech_template, "trans", 0, True)]
    kanjis = [_remove_refs(x["value"]) for x in _scrap_stat_with_prefix(tech_template, "kan", 0, True)]
    romajis = [_remove_refs(x["value"]) for x in _scrap_stat_with_prefix(tech_template, "rom", 0, True)]
    dubs = [_remove_refs(x["value"]) for x in _scrap_stat_with_prefix(tech_template, "d", 0, True)]
    descriptions = [_remove_refs(x["value"]) for x in _scrap_stat_with_prefix(tech_template, "desc", 0, True)]

    techs = []
    for i in range(len(names)):
        if not names[i]:
            continue
        techs.append({
            "name": names[i],
            "translation": translations[i] if i < len(translations) else "",
            "kanji": kanjis[i] if i < len(kanjis) else "",
            "romaji": romajis[i] if i < len(romajis) else "",
            "dub_name": dubs[i] if i < len(dubs) else "",
            "description": descriptions[i] if i < len(descriptions) else "",
        })

    digi_obj.setdefault(digimon, {})["attack_techniques"] = techs
    return True


def get_gallery_images(digimon: str, wikitext: str, digi_obj: dict) -> None:
    """Parse image gallery from the IG template."""
    parsed = wtp.parse(wikitext)
    image_list = []
    for template in parsed.templates:
        if template.name.strip() == "IG" and template.arguments:
            images = _scrap_stat_with_prefix(template, "i", 1)
            for idx, img in enumerate(images, start=1):
                caption = ""
                if template.has_arg(f"c{idx}"):
                    caption = _recursive_parse_template(
                        _replace_breaks(template.get_arg(f"c{idx}").value.strip())
                    )
                image_list.append({
                    "image": img["value"].split("<")[0].split("!")[0],
                    "caption": caption.strip().replace("\n", " "),
                })
    digi_obj.setdefault(digimon, {})["image_gallery"] = image_list


# ---------------------------------------------------------------------------
# Evolution parsing
# ---------------------------------------------------------------------------

def _check_wikilink_is_reference(link: wtp.WikiLink) -> bool:
    parent = link.parent(type_="Template")
    if parent:
        return wtp.Template(parent.string).name in ("ref", "rfc", "rfe", "refd")
    return False


def _check_wikilink_is_in_note(link: wtp.WikiLink) -> bool:
    parent = link.parent(type_="Template")
    if parent:
        return wtp.Template(parent.string).name == "note"
    return False


def _deep_search_digi(name: str, digi_obj: dict) -> tuple[bool, str | None]:
    for key, digi in digi_obj.items():
        if "name" not in digi:
            continue
        if (
            ("redirected_names" in digi and name in digi["redirected_names"])
            or name == digi["name"]
            or (isinstance(digi.get("alt_names", {}).get("other_names"), dict)
                and name == digi["alt_names"]["other_names"].get("value"))
        ):
            return True, key
        dub_values = [d["value"].lower() for d in digi.get("alt_names", {}).get("dub_names", []) if d.get("value")]
        if name.lower() in dub_values:
            return True, key
    return False, None


def _deep_search_non_digi(name: str, non_digi_obj: dict) -> tuple[bool, str | None]:
    if name in non_digi_obj:
        return True, name
    for key, entity in non_digi_obj.items():
        if name in entity.get("redirected_names", []):
            return True, key
    return False, None


def _process_evo_simple(
    evo_text: str,
    evo_type: str,
    digi_obj: dict,
    non_digi_obj: dict,
) -> dict:
    evo_obj = {
        "is_special_evo": False,
        "special_evo_type": "",
        "unknown_param": [],
        "references": [],
        "name": "",
        "name_text": "",
        "has_fusees": False,
        "link": "",
        "conditions": "",
        "type": evo_type,
    }

    if evo_type in ("digimon", "non_digimon", "any"):
        split_pos = evo_text.lower().find("with ")
        if split_pos == -1:
            split_pos = evo_text.lower().find("including ")
        has_fusees = split_pos != -1
        evo_obj["has_fusees"] = has_fusees

        evo_raw = evo_text[:split_pos] if has_fusees else evo_text
        fusees_raw = evo_text[split_pos:] if has_fusees else ""

        evo_parse = wtp.parse(_replace_ref_tag_with_template(evo_raw))
        for link in evo_parse.wikilinks:
            if _check_wikilink_is_reference(link) or _check_wikilink_is_in_note(link):
                continue
            if evo_type == "digimon":
                if link.title in digi_obj:
                    evo_obj["name"] = link.title
                elif _deep_search_digi(link.title, digi_obj)[0]:
                    evo_obj["name"] = _deep_search_digi(link.title, digi_obj)[1]
                elif link.title.lower() == "evolution":
                    evo_obj["is_special_evo"] = True
                    evo_obj["special_evo_type"] = link.text
                else:
                    evo_obj["unknown_param"].append(link.title)
            elif evo_type == "non_digimon":
                found, key = _deep_search_non_digi(link.title, non_digi_obj)
                if found:
                    evo_obj["name"] = key
                    evo_obj["name_text"] = (link.text or "").strip()
                else:
                    evo_obj["unknown_param"].append(link.title)
            elif evo_type == "any":
                evo_obj["name_text"] = (link.text or "").strip()

        if has_fusees:
            condition_parse = wtp.parse(_replace_ref_tag_with_template(fusees_raw))
            evo_obj["conditions"] = condition_parse.plain_text(
                replace_wikilinks=False,
                replace_templates=_template_replacer_refs,
            )

        for template in wtp.parse(_replace_ref_tag_with_template(evo_text)).templates:
            if template.name == "rfc":
                args = template.arguments
                if len(args) == 2:
                    evo_obj["references"].append(f"Card: {args[0].value}-{args[1].value}")
                elif len(args) == 1:
                    evo_obj["references"].append(f"Card: {args[0].value}")
            elif template.name == "note":
                evo_obj["references"].append(
                    template.plain_text(replace_templates=_template_replacer_refs)
                )
            elif template.name == "ref":
                ref = template.plain_text(replace_templates=_template_replacer)
                if ref:
                    evo_obj["references"].append(ref)

    else:
        if evo_type in ("egg", "xros"):
            for template in wtp.parse(evo_text).templates:
                evo_obj["references"].append(
                    template.plain_text(replace_templates=_template_replacer)
                )
        elif evo_type == "text":
            evo_obj["name_text"] = wtp.parse(evo_text).plain_text(
                replace_templates=_template_replacer
            )
        elif evo_type == "card":
            links = wtp.parse(evo_text).wikilinks
            if links:
                card_link = links[0]
                evo_obj["name_text"] = card_link.text or ""
                evo_obj["link"] = card_link.target
            for template in wtp.parse(evo_text).templates:
                if template.name == "rfc":
                    args = template.arguments
                    if len(args) == 2:
                        evo_obj["references"].append(f"{args[0].value}-{args[1].value}")
                    elif len(args) == 1:
                        evo_obj["references"].append(args[0].value)

    return evo_obj


def _process_evo_list_simple(
    evo_list: list[str],
    digi_obj: dict,
    non_digi_obj: dict,
) -> list[dict]:
    prc_list = []
    for evo in evo_list:
        evo_obj: dict = {}
        evo_obj["major"] = evo.strip().startswith("'''")
        evo = evo.replace("'''", "").replace("''", "").replace("\u200e", "")
        evo_parse = wtp.parse(_remove_refs(evo))

        if evo_parse.wikilinks:
            i = 0
            while i < len(evo_parse.wikilinks) and _check_wikilink_is_reference(evo_parse.wikilinks[i]):
                i += 1
            if i < len(evo_parse.wikilinks):
                evo_title = evo_parse.wikilinks[i].title
                if evo_title in digi_obj or _deep_search_digi(evo_title, digi_obj)[0]:
                    evo_obj.update(_process_evo_simple(evo, "digimon", digi_obj, non_digi_obj))
                elif evo_title in (
                    "Digimon Card Game Colors and Levels",
                    "Digimon World: Digital Card Arena Attributes and Levels",
                    "Digimon World: Digital Card Battle Attributes and Levels",
                    "Battle Spirits Card Game Colors and Levels",
                    "Digimon Card Game DigiXros",
                ):
                    evo_obj.update(_process_evo_simple(evo, "card", digi_obj, non_digi_obj))
                elif evo_parse.plain_text().strip().startswith("Any"):
                    evo_obj.update(_process_evo_simple(evo, "any", digi_obj, non_digi_obj))
                elif evo_title.lower() == "digitama":
                    evo_obj.update(_process_evo_simple(evo, "egg", digi_obj, non_digi_obj))
                elif evo_title.lower() == "digixros":
                    evo_obj.update(_process_evo_simple(evo, "xros", digi_obj, non_digi_obj))
                elif _deep_search_non_digi(evo_title, non_digi_obj)[0]:
                    evo_obj.update(_process_evo_simple(evo, "non_digimon", digi_obj, non_digi_obj))
                else:
                    evo_obj.update(_process_evo_simple(evo, "text", digi_obj, non_digi_obj))
            else:
                evo_obj.update(_process_evo_simple(evo, "text", digi_obj, non_digi_obj))
        else:
            evo_obj.update(_process_evo_simple(evo, "text", digi_obj, non_digi_obj))

        if "name" in evo_obj:
            prc_list.append(evo_obj)
    return prc_list


def get_evolutions_per_digimon(
    digimon: str,
    wikitext: str,
    digi_obj: dict,
    non_digi_obj: dict,
) -> None:
    """Parse evolve_from and evolve_to sections for a single digimon."""
    digi_obj.setdefault(digimon, {})
    parsed = wtp.parse(wikitext)
    for section in parsed.get_sections():
        if not section.title:
            continue
        title_lower = section.title.strip().lower()
        lists = section.get_lists()
        items = [item for lst in lists for item in lst.items] if lists else []
        if title_lower == "evolves from":
            digi_obj[digimon]["evolve_from"] = _process_evo_list_simple(items, digi_obj, non_digi_obj)
        elif title_lower == "evolves to":
            digi_obj[digimon]["evolve_to"] = _process_evo_list_simple(items, digi_obj, non_digi_obj)


# ---------------------------------------------------------------------------
# Non-digimon link resolution
# ---------------------------------------------------------------------------

def _get_unknown_evo_links(
    evo_list: list[str],
    digi_obj: dict,
    non_digi_obj: dict,
    redirected_names: list[str],
) -> list[str]:
    keys = []
    for evo in evo_list:
        evo = evo.replace("'''", "").replace("''", "").replace("\u200e", "")
        evo = _remove_refs(evo)
        evo_parse = wtp.parse(evo)
        if evo_parse.plain_text().strip().startswith("Any"):
            continue
        for link in evo_parse.wikilinks:
            if _check_wikilink_is_reference(link):
                continue
            t = link.title
            if not (
                t in digi_obj
                or t in non_digi_obj
                or t in redirected_names
                or t.lower() in ("digitama", "digixros")
                or "Category" in t
            ):
                keys.append(t)
    return keys


def find_and_resolve_evo_links(
    page_content: dict,
    digi_obj: dict,
    non_digi_obj: dict,
    session: requests.Session,
) -> None:
    """
    Scan all evolutions sections to find unknown wiki links, then fetch their
    pages and classify them as digimon aliases or non-digimon entries.
    Updates digi_obj and non_digi_obj in-place.
    """
    evo_keys: set[str] = set()
    redirected_names_list: list[str] = [
        name
        for d in digi_obj.values()
        for name in d.get("redirected_names", [])
    ]

    for body in page_content.values():
        parsed = wtp.parse(body.get("wikitext", ""))
        for section in parsed.get_sections():
            if section.title and section.title.strip().lower() in ("evolves from", "evolves to"):
                lists = section.get_lists()
                items = [item for lst in lists for item in lst.items] if lists else []
                evo_keys.update(
                    _get_unknown_evo_links(items, digi_obj, non_digi_obj, redirected_names_list)
                )

    if not evo_keys:
        return

    for titles in _get_digimon_list_for_api(list(evo_keys)):
        params = f"action=query&prop=revisions&titles={titles}&rvslots=*&rvprop=content&format=json"
        data = _api_get(session, params)

        for norm in data["query"].get("normalized", []):
            if norm["to"] in digi_obj:
                digi_obj[norm["to"]].setdefault("redirected_names", [])
                if norm["from"] not in digi_obj[norm["to"]]["redirected_names"]:
                    digi_obj[norm["to"]]["redirected_names"].append(norm["from"])

        for _, body in data["query"]["pages"].items():
            title = body["title"]
            if "missing" in body:
                non_digi_obj.setdefault(title, {"wikitext": "", "redirected_names": []})
                continue
            wikitext = body["revisions"][0]["slots"]["main"]["*"]
            if wikitext.strip().lower().startswith("#redirect"):
                match = re.search(r"\[\[(.*?)\]\]", wikitext)
                if match:
                    target = match.group(1)
                    if target in digi_obj:
                        digi_obj[target].setdefault("redirected_names", [])
                        if title not in digi_obj[target]["redirected_names"]:
                            digi_obj[target]["redirected_names"].append(title)
                    elif target not in digi_obj:
                        non_digi_obj.setdefault(title, {"redirected_names": []})
                        non_digi_obj[title]["wikitext"] = wikitext
            elif title not in non_digi_obj:
                non_digi_obj[title] = {"wikitext": wikitext, "redirected_names": []}

    # Resolve redirects within non_digi_obj too
    non_digi_obj, _ = resolve_redirects(session, non_digi_obj)


# ---------------------------------------------------------------------------
# Top-level sync entry point
# ---------------------------------------------------------------------------

def sync_digimon(
    refresh_all: bool = False,
    existing_revisions: dict[str, str] | None = None,
    existing_non_digi: dict | None = None,
) -> tuple[dict, dict, list[str]]:
    """
    Main sync function for Cloud Functions.

    Args:
        refresh_all: If True, scrape all digimon regardless of revision date.
        existing_revisions: {name: last_scraped_revision} from Firestore (for incremental).
        existing_non_digi: Current non_digi_obj from Firestore (used for evo link resolution).

    Returns:
        (digi_obj, non_digi_obj, deleted_names)
        - digi_obj: {name: parsed_digimon_data} for all updated digimon
        - non_digi_obj: {name: entity_data} for non-digimon entities discovered
        - deleted_names: list of digimon names absent from wikimon (to delete from Firestore)
    """
    if existing_revisions is None:
        existing_revisions = {}
    if existing_non_digi is None:
        existing_non_digi = {}

    session = _make_session()
    digi_obj: dict = {}
    non_digi_obj: dict = dict(existing_non_digi)

    # 1. Fetch current digimon list from wikimon
    logger.info("Fetching digimon list from wikimon...")
    digimon_list = get_digimon_list(session)
    if not digimon_list:
        raise RuntimeError("No digimon fetched from wikimon — server may be down.")

    # 2. Detect deleted digimon
    current_set = set(digimon_list)
    existing_set = set(existing_revisions.keys())
    deleted_names = list(existing_set - current_set)
    logger.info(f"Deleted digimon: {deleted_names}")

    # 3. Determine which pages need updating
    revision_map: dict[str, str] = {}
    if refresh_all:
        to_update = digimon_list
    else:
        logger.info("Checking revision timestamps...")
        revision_map = get_revision_timestamps(digimon_list, session)
        to_update = [
            name for name, ts in revision_map.items()
            if name not in existing_revisions
            or not existing_revisions[name]          # empty string → treat as never synced
            or _get_date(existing_revisions[name]) < _get_date(ts)
        ]
        logger.info(f"Pages to update: {len(to_update)}")

    if not to_update:
        logger.info("Everything is up-to-date.")
        return digi_obj, non_digi_obj, deleted_names

    # 4. Fetch wikitext for changed pages
    logger.info("Fetching wikitext...")
    page_content = get_page_wikitexts(to_update, session)
    page_content, _ = resolve_redirects(session, page_content)

    # 5. Resolve evo links → populate non_digi_obj
    logger.info("Resolving evolution links...")
    find_and_resolve_evo_links(page_content, digi_obj, non_digi_obj, session)

    # 6. Scrape DRB index (needs full content, not just updated pages)
    #    For incremental syncs, only index updated pages; full sync indexes all.
    scrap_drb_index(page_content, digi_obj)

    # 7. Parse each updated digimon
    total_pages = len(page_content)
    logger.info(f"Parsing {total_pages} digimon pages...")
    for idx, (digimon, body) in enumerate(page_content.items(), start=1):
        if idx % 100 == 0 or idx == total_pages:
            logger.info(f"Parsing progress: {idx}/{total_pages}")
        wikitext = body.get("wikitext", "")
        digi_obj.setdefault(digimon, {})
        digi_obj[digimon]["redirected_names"] = body.get("redirected_names", [])
        # Store the wikimon revision timestamp so incremental syncs can skip unchanged pages
        digi_obj[digimon]["_revision_date"] = revision_map.get(digimon, "")
        scrap_descriptions(digimon, wikitext, digi_obj)
        scrap_stats(digimon, wikitext, digi_obj)
        get_gallery_images(digimon, wikitext, digi_obj)
        scrap_attack_techs(digimon, wikitext, digi_obj)
        get_evolutions_per_digimon(digimon, wikitext, digi_obj, non_digi_obj)

    logger.info(f"Sync complete. Updated: {len(digi_obj)}, Deleted: {len(deleted_names)}")
    return digi_obj, non_digi_obj, deleted_names
