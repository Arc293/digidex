import random
import requests
import re
import urllib.parse
import json
import sys, traceback
from datetime import datetime
from bs4 import BeautifulSoup
import wikitextparser as wtp
from collections import Counter
from scrap_digimon import scrap_stat_with_prefix, resolve_redirects, get_digimon_list_for_api, scrap_single_stat
from collections import Counter

def load_content_json():
    content = {}
    try:
        with open('wikimon_tcg_scrap.json') as infile:
            content = json.load(infile)
    except Exception:
        print("Exception in user code:")
        print("-"*60)
        traceback.print_exc(file=sys.stdout)
        print("-"*60)
    return content

def load_card_json():
    content = {}
    try:
        with open('tcg_scrap.json') as infile:
            content = json.load(infile)
    except Exception:
        print("Exception in user code:")
        print("-"*60)
        traceback.print_exc(file=sys.stdout)
        print("-"*60)
    return content

def sanitise_json():
    try:
        with open('wikimon_tcg_scrap.json') as infile:
            content = json.load(infile)
            keysToRemove = []
            for key in content.keys():
                if key.startswith('User:') or key.startswith('Template:'):
                    keysToRemove.append(key)
            for key in keysToRemove:
                del content[key]
            with open('wikimon_tcg_scrap.json', 'w') as outfile:
                json.dump(content, outfile, sort_keys=True)
    except Exception:
        print("Exception in user code:")
        print("-"*60)
        traceback.print_exc(file=sys.stdout)
        print("-"*60)

def get_date(date_string):
    return datetime.fromisoformat(date_string)


def get_card_list(session=None):
    try:
        card_list = []
        if session == None:
            session = requests.Session()
        # card from Category: List_of_cards
        params = 'action=query&format=json&list=categorymembers&cmpageid=8832&cmlimit=500'
        continueparam = ''
        while True:
            response = session.get(url='https://wikimon.net/api.php',
                        params= params+continueparam).json()
            card_list.extend([card['title'] for card in response['query']['categorymembers'] 
                                if (not card['title'].startswith('Category:') and not card['title'].startswith('User:') and not card['title'].startswith('Template:'))])
            if 'continue' in response:
                continueparam = f'&cmcontinue={response["continue"]["cmcontinue"]}'
            else:
                break
        
    except Exception:
        print("Exception in user code:")
        print("-"*60)
        traceback.print_exc(file=sys.stdout)
        print("-"*60)
        return []
    return card_list


def scrap_and_save_page_content():
    # card_list = load_json()
    page_object = {}
    card_obj = {}
    try:
        with open('wikimon_tcg_scrap.json') as infile:
            page_object = json.load(infile)
    except Exception:
        print("Exception in user code:")
        print("-"*60)
        traceback.print_exc(file=sys.stdout)
        print("-"*60)
    try:
        with open('card_list.json') as infile:
            card_obj = json.load(infile)
    except Exception:
        print("Exception in user code:")
        print("-"*60)
        traceback.print_exc(file=sys.stdout)
        print("-"*60)

    changed = False
    last_update = None
    try:
        card_to_update = []
        session = requests.Session()
        card_list = get_card_list(session=session)
        # absent_card = get_absent_card(card_obj, card_list)
        # if len(absent_card)>0:
        #     changed = True
        #     for del_card in absent_card:
        #         del page_object[del_card]
        #         del card_obj[del_card]
        #         print(f'Entry for {del_card} has been removed from wiki (redirected to other page)')
        #     with open('card_list.json', 'w') as outfile:
        #         json.dump(card_obj, outfile, sort_keys=True)
        # Get last revision timestamps from API
        for titles in get_digimon_list_for_api(value_list=card_list):
            # print(titles)
            
            params = f'action=query&prop=revisions&titles={titles}&rvslots=*&rvprop=timestamp&format=json'
            data = session.get(url='https://wikimon.net/api.php',
                            params= params)
            data_obj = data.json()
            pages = data_obj['query']['pages']

            for id,body in pages.items():
                last_update = body
                card = body['title']
                date = body['revisions'][0]['timestamp']
                if card not in page_object:
                    page_object[card] = {}
                    changed = True

                if 'revision_date' not in page_object[card] or get_date(page_object[card]['revision_date']) < get_date(date):
                    page_object[card]['revision_date'] = date
                    changed = True
                    print(f'Page for {card} has new updates on: {date}')
                    card_to_update.append(card)
                else:
                    # print(f'Page for {card} is already up-to-date')
                    if 'wikitext' not in page_object[card] or 'redirected_names' not in page_object[card]:
                        card_to_update.append(card)
        if not len(card_to_update):
            print("Everything is up-to-date!")
        for titles in get_digimon_list_for_api(card_to_update):
            params = f'action=query&prop=revisions&titles={titles}&rvslots=*&rvprop=content&format=json'
            data = session.get(url='https://wikimon.net/api.php',
                            params= params)
            data_obj = data.json()
            pages = data_obj['query']['pages']

            for id,body in pages.items():
                card = body['title']
                wikitext = body['revisions'][0]['slots']['main']['*']
                page_object[card]['wikitext'] = wikitext
                changed = True
                print("Page content added for: ",card)
        print(f'Number of pages updated: {len(card_to_update)}')
        page_object, changed_redirected = resolve_redirects(session, page_object)
        changed = changed or changed_redirected
    except Exception:
        print("Exception in user code:")
        print("-"*60)
        traceback.print_exc(file=sys.stdout)
        print("-"*60) 
        print(last_update)
    finally:
        if changed:
            with open('wikimon_tcg_scrap.json', 'w') as outfile:
                json.dump(page_object, outfile, sort_keys=True)

def get_template_types(content:dict):
    types = set()
    for x in content.values():
        parsed = wtp.parse(x['wikitext'])
        template_name = parsed.templates[0].name.strip()
        types.add(template_name)
    titles = '|'.join([f'Template:{x}' for x in types])
    session = requests.Session()
    params = f'action=query&prop=revisions&titles={titles}&rvslots=*&rvprop=content&format=json'
    data = session.get(url='https://wikimon.net/api.php',
                    params= params)
    data_obj = data.json()
    pages = data_obj['query']['pages']
    type_param_map = {}
    for id,body in pages.items():
        title = body['title'].split(':', 1)[1]
        # print(body)
        wikitext = body['revisions'][0]['slots']['main']['*']
        wkparsed = wtp.parse(wikitext)
        params = set([param.name.strip() for param in wkparsed.parameters if param.name.strip() != "1"])
        type_param_map[title] = list(params)
        type_param_map[title].sort()
    # with open('type_param_map.json', 'w') as outfile:
    #     json.dump(type_param_map, outfile, sort_keys=True)
    return type_param_map


def get_content_dj(content:wtp.Template, card_obj:dict, name:str):
    if name not in card_obj:
        card_obj[name] = {}
    card_obj[name]['game_code'] = 'DJ'
    card_obj[name]['name'] = scrap_single_stat(content, 'name')
    card_obj[name]['series'] = scrap_single_stat(content, 'series')
    serial_number = scrap_single_stat(content, 'sn')
    card_obj[name]['serial_number'] = serial_number

    previous_card = scrap_single_stat(content, 'prev')
    card_obj[name]['previous_card'] = f'{serial_number}-{previous_card}' if len(previous_card)>0 else ''

    next_card = scrap_single_stat(content, 'next')
    card_obj[name]['next_card'] = f'{serial_number}-{next_card}' if len(next_card)>0 else ''

    type_map = {'a': 'Attack', 's': 'Support', 'g': 'Guard'}
    card_obj[name]['card_type'] = type_map[scrap_single_stat(content, 'asg')]

    card_obj[name]['atk'] = scrap_single_stat(content, 'atk')
    card_obj[name]['def'] = scrap_single_stat(content, 'def')
    card_obj[name]['spd'] = scrap_single_stat(content, 'spd')
    card_obj[name]['sup'] = scrap_single_stat(content, 'sup')

    card_obj[name]['level'] = scrap_single_stat(content, 'l')
    card_obj[name]['type'] = scrap_single_stat(content, 't')

    card_obj[name]['affiliation'] = [x['value'] for x in scrap_stat_with_prefix(content, 'other', 1) if len(x['value']) > 0]

    card_obj[name]['cost'] = f"{scrap_single_stat(content, 'cost')}GB"
    card_obj[name]['reader_capacity'] = f"{scrap_single_stat(content, 'ldr')}GB"
    card_obj[name]['species'] = scrap_single_stat(content, 'species')
    card_obj[name]['ex'] = scrap_single_stat(content, 'ex')

    card_obj[name]['skill'] = {}
    card_obj[name]['skill']['name'] = scrap_single_stat(content, 'skill')
    card_obj[name]['skill']['description'] = scrap_single_stat(content, 'skilld')

    card_obj[name]['profile'] = scrap_single_stat(content, 'p')

    card_obj[name]['images'] = []
    card_obj[name]['images'].append({'name': f'Djt-{name}_front.jpg', 'type': 'front'})
    card_obj[name]['images'].append({'name': f'Djt-{name}_back.jpg', 'type': 'back'})

# def get_content_dcdapm(content:wtp.Template, card_obj:dict, name:str):
#     if name not in card_obj:
#         card_obj[name] = {}
#     card_obj[name]['game_code'] = 'DCDAPM'
#     card_obj[name]['name'] = scrap_single_stat(content, 'n')

#     card_obj[name]['series'] = scrap_single_stat(content, 'series')
#     serial_number = scrap_single_stat(content, 'sn')
#     card_obj[name]['serial_number'] = serial_number

#     previous_card = scrap_single_stat(content, 'prev')
#     card_obj[name]['previous_card'] = f'{previous_card} (DCDAPM)' if len(previous_card)>0 else ''

#     next_card = scrap_single_stat(content, 'next')
#     card_obj[name]['next_card'] = f'{next_card} (DCDAPM)' if len(next_card)>0 else ''

#     card_obj[name]['rarity'] = scrap_single_stat(content, 'r')
#     card_obj[name]['grade'] = scrap_single_stat(content, 'g')
#     card_obj[name]['type'] = scrap_single_stat(content, 't')

#     card_obj[name]['hp'] = scrap_single_stat(content, 'hp')
#     card_obj[name]['pow'] = scrap_single_stat(content, 'pow')
#     card_obj[name]['def'] = scrap_single_stat(content, 'def')
#     card_obj[name]['spd'] = scrap_single_stat(content, 'spd')

#     card_obj[name]['profile'] = scrap_single_stat(content, 'd')

#     card_obj[name]['normal_attack'] = {}
#     card_obj[name]['normal_attack']['name'] = scrap_single_stat(content, 'nattack')
#     card_obj[name]['normal_attack']['description'] = scrap_single_stat(content, 'nattackd')

#     card_obj[name]['app_technique'] = {}
#     card_obj[name]['app_technique']['name'] = scrap_single_stat(content, 'apptec')
#     card_obj[name]['app_technique']['cost'] = scrap_single_stat(content, 'appteccost')
#     card_obj[name]['app_technique']['type'] = scrap_single_stat(content, 'apptectype')
#     card_obj[name]['app_technique']['description'] = scrap_single_stat(content, 'apptecd')

#     card_obj[name]['ability'] = {}
#     card_obj[name]['ability']['name'] = scrap_single_stat(content, 'abl')
#     card_obj[name]['ability']['description'] = scrap_single_stat(content, 'abld')

#     card_obj[name]['gattai'] = {}
#     card_obj[name]['gattai']['name'] = scrap_single_stat(content, 'gattai')
#     card_obj[name]['gattai']['cost'] = scrap_single_stat(content, 'gcost')
#     card_obj[name]['gattai']['partner'] = scrap_single_stat(content, 'p2')
#     if not len(card_obj[name]['gattai']['partner']):
#         card_obj[name]['gattai']['partner'] = scrap_single_stat(content, 'partner')
#     card_obj[name]['gattai']['normal_attack'] = scrap_single_stat(content, 'gnattack')
#     card_obj[name]['gattai']['app_technique'] = {}
#     card_obj[name]['gattai']['app_technique']['name'] = scrap_single_stat(content, 'gapptec')
#     card_obj[name]['gattai']['app_technique']['type'] = scrap_single_stat(content, 'gapptectype')
#     card_obj[name]['gattai']['app_technique']['cost'] = scrap_single_stat(content, 'gappcost')

#     card_obj[name]['images'] = []
#     card_obj[name]['images'].append({'name': f'Dcda-{serial_number}_front.jpg', 'type': 'front'})
#     card_obj[name]['images'].append({'name': f'Dcda-{serial_number}_back.jpg', 'type': 'back'})

def get_content_dcdapm(params):
    """
    Convert DCDAPM wikitext parameters into a Python dictionary.
    Input: params -> dictionary with exact wikitext keys
    Output: structured dictionary with all card info
    """
    card = {}

    # Basic info
    card['series'] = params.get('series')
    card['sn'] = params.get('sn')
    card['prev'] = params.get('prev')
    card['next'] = params.get('next')
    card['rarity'] = params.get('r')
    card['grade'] = params.get('g')
    card['level'] = params.get('l')
    card['type'] = params.get('t')

    # Appmon info
    card['appmon'] = {
        'name': params.get('n'),
        'pagename': params.get('n2'),
        'plus_name': params.get('plus'),
        'plus_pagename': params.get('plus2'),
        'attribute': params.get('att'),
    }

    # Stats
    card['stats'] = {
        'hp': params.get('hp'),
        'power': params.get('pow'),
        'defense': params.get('def'),
        'speed': params.get('spd'),
    }

    # Profile
    card['profile'] = {
        'english': params.get('d'),
        'japanese': params.get('dj'),
    }

    # Attacks
    card['normal_attack'] = {
        'name': params.get('nattack'),
        'name_jp': params.get('nattackj'),
        'description': params.get('nattackd'),
        'description_jp': params.get('nattackdj'),
    }

    # App technique
    card['app_technique'] = {
        'name': params.get('apptec'),
        'name_jp': params.get('apptecj'),
        'cost': params.get('appteccost'),
        'type': params.get('apptectype'),
        'description': params.get('apptecd'),
        'description_jp': params.get('apptecdj'),
    }

    # Ability
    card['ability'] = {
        'name': params.get('abl'),
        'name_jp': params.get('ablj'),
        'description': params.get('abld'),
        'description_jp': params.get('abldj'),
    }

    # Gattai / Applink
    card['gattai'] = {
        'name': params.get('gattai'),
        'applink': params.get('applink'),
        'cost': params.get('gcost'),
        'partner': params.get('partner'),
        'partner_pagename': params.get('p2'),
        'normal_attack': {
            'name': params.get('gnattack'),
            'name_jp': params.get('gnattackj'),
        },
        'app_technique': {
            'name': params.get('gapptec'),
            'name_jp': params.get('gapptecj'),
            'type': params.get('gapptectype'),
            'cost': params.get('gappcost'),
        }
    }

    # Promo / Released info
    card['released_with'] = {
        'en': params.get('pr'),
        'jp': params.get('prj'),
    }

    return card


def get_content_sdtdm(content:wtp.Template, card_obj:dict, name:str):
    if name not in card_obj:
        card_obj[name] = {}
    card_obj[name]['game_code'] = 'SDTDM'
    card_obj[name]['name'] = scrap_single_stat(content, 'name')
    card_obj[name]['series'] = scrap_single_stat(content, 'series')
    serial_number = scrap_single_stat(content, 'sn')
    card_obj[name]['serial_number'] = serial_number

    previous_card = scrap_single_stat(content, 'prev')
    card_obj[name]['previous_card'] = f'{serial_number}-{previous_card}' if len(previous_card)>0 else ''

    next_card = scrap_single_stat(content, 'next')
    card_obj[name]['next_card'] = f'{serial_number}-{next_card}' if len(next_card)>0 else ''

    card_obj[name]['technique'] = {}
    card_obj[name]['technique']['name'] = scrap_single_stat(content, 'tech')
    card_obj[name]['technique']['description'] = scrap_single_stat(content, 'techd')

    card_obj[name]['profile'] = scrap_single_stat(content, 'p')
    card_obj[name]['illustrator'] = scrap_single_stat(content, 'i')
    card_obj[name]['rarity'] = scrap_single_stat(content, 'r')
    card_obj[name]['effect'] = scrap_single_stat(content, 'e')

    card_obj[name]['images'] = []
    card_obj[name]['images'].append({'name': f'{name.lower().capitalize()}_front.jpg', 'type': 'front'})
    card_obj[name]['images'].append({'name': f'{name.lower().capitalize()}_back.jpg', 'type': 'back'})

def get_content_apmcg(params):
    """
    Generate a JSON object for a Digimon card,
    merging English and Japanese info into single objects.
    """
    
    def gather_requirements(prefix):
        reqs = []
        for i in range(1, 6):
            parts = []
            for key in [f"{prefix}{i}", f"{prefix}{i}a", f"{prefix}{i}b", f"{prefix}{i}o", f"{prefix}{i}xo", f"{prefix}{i}d"]:
                val = params.get(key)
                if val:
                    parts.append(str(val))
            if parts:
                reqs.append(" × ".join(parts))
        return reqs

    def gather_sequence(prefix, max_seq=4):
        seq = []
        for i in range(1, max_seq + 1):
            val = params.get(f"{prefix}{i}")
            if val:
                seq.append(val)
        return seq if seq else None

    categories = [
        "List of Cards",
        params.get("series"),
        f"List of {params.get('n2')} Cards" if params.get("n2") else f"List of {params.get('n')} Cards" if params.get("n") else None,
        f"{params.get('at')} Appmon Cards" if params.get("at") else None,
        f"{params.get('g')} Appmon Cards" if params.get("g") else None,
        f"List of Cards Released in {params.get('yom')}" if params.get("yom") else None
    ]
    categories = [c for c in categories if c]

    return {
        "name": params.get("n"),
        "alt_name": params.get("n2"),
        "series": params.get("series"),
        "illustrator": params.get("i"),
        "rarity": params.get("rarity"),
        "grade": params.get("l"),
        "app": params.get("app"),
        "type": params.get("at"),
        "virus": params.get("virus"),
        "extra": {
            "ext": params.get("ext"),
            "ext2": params.get("ext2"),
            "ext3": params.get("ext3")
        },
        "images": {
            "main": f"Image:{params.get('n')}.jpg" if params.get("n") else None,
            "icons": {
                "g_icon": f"{params.get('n')}_icon.png" if params.get("n") else None,
                "l_icon": f"APMCG_{params.get('l')}_icon.png" if params.get("l") else None
            }
        },
        "battle_info": {
            "battle_type": params.get("bt"),
            "requirements": gather_requirements("e")
        },
        "attacks": {
            "A": {key: params.get(key) for key in ["a", "apt", "applink", "applinkj"] if params.get(key)},
            "B": {key: params.get(key) for key in ["b", "bpt"] if params.get(key)},
            "C": {key: params.get(key) for key in ["c", "cpt"] if params.get(key)},
            "LP": params.get("lp"),
            "sequence": gather_sequence("s", 4)
        },
        "plugs": params.get("plug"),
        "notes": params.get("note"),
        "categories": categories
    }

def get_content_ae(params):
    """
    Transform a flat card parameter dict into a structured card dict.
    
    :param params: dict containing template parameters
    :return: structured dict with schema
    """
    card = {
        "name": params.get("n") or params.get("n2"),
        "alt_name": params.get("n2"),
        "series": params.get("series"),
        "previous": params.get("prev"),
        "next": params.get("next"),
        "images": [],
        "stats": {
            "cost": params.get("cs"),
            "speed": params.get("sp"),
            "code_effect": params.get("ce"),
            "hp": params.get("hp"),
            "battle_type": params.get("bt"),
            "attribute": params.get("at"),
            "type": params.get("t"),
            "field": params.get("f")
        },
        "evolutions": [],
        "attacks": [],
        "special_abilities": [],
        "notes": params.get("note"),
        "release_info": {
            "series_type": params.get("bos"),
            "year_of_release": params.get("yom")
        }
    }

    # Images (handle up to 4 images as in template)
    for i in range(1, 5):
        img_key = "i" if i == 1 else f"i{i}"
        img_title_key = "ih" if i == 1 else f"i{i}h"
        if params.get(img_key):
            card["images"].append({
                "title": params.get(img_title_key),
                "file": params[img_key]
            })

    # Evolutions (e1-e5)
    for i in range(1, 6):
        evo_key = f"e{i}"
        evo_desc_key = f"e{i}d"
        if params.get(evo_key) or params.get(evo_desc_key):
            card["evolutions"].append({
                "stage": f"e{i}",
                "evolution": params.get(evo_key) or params.get(evo_desc_key)
            })

    # Attacks (A, B, C)
    for label in ["a", "b", "c"]:
        if params.get(label):
            card["attacks"].append({
                "label": label.upper(),
                "name": params[label],
                "points": params.get(f"{label}pt"),
                "field": params.get("f")
            })

    # Special abilities (b1-b4, s1-s4)
    for key_prefix in ["b", "s"]:
        for i in range(1, 5):
            key = f"{key_prefix}{i}"
            if params.get(key):
                card["special_abilities"].append(params[key])

    return card

def get_content_apmcgo(params, name):
    return {
        "prev": params.get("prev"),
        "next": params.get("next"),
        "sn": params.get("sn"),
        "series": params.get("series"),
        "image": name + ".jpg" if name else None,
        "rarity": params.get("rarity"),
        "activation_timing": params.get("time"),
        "english": {
            "name": params.get("n"),
            "name_link": params.get("nlink"),
            "comments": [c for c in [params.get("com"), params.get("com2"), params.get("com3"), params.get("com4")] if c],
            "description": params.get("d"),
            "requirements": params.get("req"),
            "category": params.get("cat"),
            "effects": [r for r in [params.get("r1"), params.get("r2"), params.get("r3"), params.get("r4"), params.get("r5")] if r]
        },
        "japanese": {
            "name": params.get("kan"),
            "comments": [c for c in [params.get("comj"), params.get("com2j"), params.get("com3j"), params.get("com4j")] if c],
            "description": params.get("dj"),
            "requirements": params.get("reqj"),
            "category": params.get("catj") or params.get("cat"),
            "effects": [r for r in [params.get("r1j"), params.get("r2j"), params.get("r3j"), params.get("r4j"), params.get("r5j")] if r]
        },
        "notes": params.get("note"),
        "categories": {
            "type": params.get("type"),
            "year_of_manufacture": params.get("yom")
        }
    }

def get_content_cae(params: dict) -> dict:
    """
    Converts the parameters from the Command Card wikitext into a flattened dictionary.
    """
    result = {
        "navigation": {
            "prev": params.get("prev"),
            "next": params.get("next"),
            "series": params.get("series"),
            "sn": params.get("sn", "Cα")
        },
        "image": params.get("i", f"{params.get('PAGENAME', '')}.jpg"),
        "name": {
            "english": params.get("n"),
            "japanese": params.get("nj")
        },
        "frame": params.get("frame"),
        "rarity": params.get("ce"),
        "effects": {
            "battle": [params.get(f"b{i}") for i in range(1, 5) if params.get(f"b{i}")],
            "alpha": [params.get(f"a{i}") for i in range(1, 5) if params.get(f"a{i}")]
        },
        "effects_japanese": {
            "battle": [params.get(f"b{i}j") for i in range(1, 5) if params.get(f"b{i}j")],
            "alpha": [params.get(f"a{i}j") for i in range(1, 5) if params.get(f"a{i}j")]
        },
        "categories": {
            "series": params.get("series"),
            "bos": params.get("bos"),
            "yom": params.get("yom"),
            "cost": params.get("cs"),
            "speed": params.get("sp"),
            "ce_level": params.get("ce")
        }
    }

    return result

def get_generic_content(content:dict, card_obj:dict):
    template_param_map = load_template_map()
    for title,data in content.items():
        templates = wtp.parse(data['wikitext']).templates
        template = templates[1] if templates[0].name.strip() == 'FCard' else templates[0]
        template_name = template.name.strip()
        if template_name not in card_obj:
            card_obj[template_name] = {}
        if title not in card_obj[template_name]:
            card_obj[template_name][title] = {}
        for param in template_param_map[template.name.strip()]:
            param_val = scrap_single_stat(template, param)
            if len(param_val)>0:
                card_obj[template_name][title][param] = param_val

def load_template_map():
    map = {}
    try:
        with open('type_param_map.json', 'r') as infile:
            map = json.load(infile)
    except Exception:
        print("Exception in user code:")
        print("-"*60)
        traceback.print_exc(file=sys.stdout)
        print("-"*60) 
    return map

def get_wikimon_tcg_templates(content:dict):
    types = set()
    for x in content.values():
        parsed = wtp.parse(x['wikitext'])
        template_name = parsed.templates[0].name.strip()
        types.add(template_name)
    titles = '|'.join([f'Template:{x}' for x in types])
    session = requests.Session()
    params = f'action=query&prop=revisions&titles={titles}&rvslots=*&rvprop=content&format=json'
    data = session.get(url='https://wikimon.net/api.php',
                    params= params)
    data_obj = data.json()
    pages = data_obj['query']['pages']
    template_html_data = {}
    for id,body in pages.items():
        title = body['title'].split(':', 1)[1]
        # print(body)
        wikitext = body['revisions'][0]['slots']['main']['*']
        template_html_data[title]=wikitext
    with open('template_html_data.json', 'w') as outfile:
        json.dump(template_html_data, outfile, sort_keys=True)
    # return type_param_map
    
def generate_param_info(card_obj:dict):
    counter_map = {}
    example_map = {}
    for game, cards in card_obj.items():
        counter_map[game] = Counter()
        example_map[game] = {}

        for k, card_data in cards.items():
            counter_map[game].update(card_data.keys())
            for param, param_data in card_data.items():
                if param not in example_map[game]:
                    example_map[game][param] = set()
                example_map[game][param].add(param_data)

    final_map = {}
    for game, counter in counter_map.items():
        final_map[game] = {}
        for param, count in counter.items():
            final_map[game][param] = f'Count: {count}, Examples: {[el for (el, _) in zip(example_map[game][param], range(6))]}'
    with open('param_info.json', 'w') as outfile:
        json.dump(final_map, outfile, sort_keys=True)   

def generate_html_for_card(card_data:dict, game_type:str, card_name:str):
    wikitext = wtp.Template('{{'+game_type+'}}')
    for param,value in card_data.items():
        wikitext.set_arg(param, value)
    print(wikitext.string)

def split_wikitext():
    with open('template_html_data.json', 'r') as infile:
        wiki_json = json.load(infile)
        for key, value in wiki_json.items():
            with open(f'tcg_wikitexts/{key}.txt', 'w') as outfile:
                json.dump(value, outfile)

# scrap_and_save_page_content()
# sanitise_json()
content = load_content_json()
# get_template_types(content)

card_obj = load_card_json()
# template_map = load_template_map()
# print([f'Template:{x}' for x in list(template_map.keys())])
split_wikitext()
# generate_param_info(card_obj)
# get_wikimon_tcg_templates(content)
# generate_html_for_card(card_obj['AE']['DM-001'], 'AE', 'DM-001')
# try:
#     get_generic_content(content, card_obj)
# except Exception:
#         print("Exception in user code:")
#         print("-"*60)
#         traceback.print_exc(file=sys.stdout)
#         print("-"*60) 
# finally:
#     with open('tcg_scrap.json', 'w') as outfile:
#         json.dump(card_obj, outfile, sort_keys=True)
# template = wtp.parse(content['1-001']['wikitext']).templates[0]
# get_content_dj(template,card_obj,'1-001')
# print(card_obj)