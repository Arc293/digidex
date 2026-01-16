import wikitextparser as wtp
from scrap_digimon import remove_refs, check_wikilink_is_reference, deep_search_digi, deep_search_non_digi, replace_ref_tag_with_template, load_content_json, load_json, load_non_digi_content
import requests
import json
import re

def process_evo_list(evo_list:list,digi_obj:dict, non_digi_obj:dict, session:requests.Session)->list:
    prc_list = []
    for evo in evo_list:
        evo_obj = None
        evo = evo.replace("'''", "")
        evo = evo.replace("''","").replace("\u200e","")
        evo_parse = wtp.parse(remove_refs(evo))
        if evo_parse.wikilinks:
            # evo_name = evo_parse.wikilinks[0].plain_text()
            i = 0
            while i < len(evo_parse.wikilinks) and check_wikilink_is_reference(evo_parse.wikilinks[i]):
                i += 1
            if i < len(evo_parse.wikilinks):
                evo_title = evo_parse.wikilinks[0].title
                if evo_title in digi_obj or deep_search_digi(evo_title, digi_obj)[0]:
                    evo_obj = process_evo(evo, 'digimon', digi_obj, non_digi_obj)
                # elif re.search("^any.*from.*card.*", evo_name.lower()):
                #     evo_obj['valid_card'] = evo
        if evo_obj:       
            prc_list.append(evo_obj)
    return prc_list


def process_evo(evo_text:str, evo_type:str, digi_obj:dict, non_digi_obj:dict):
    evo_obj = {'is_special_evo':False, 'special_evo_type': '', 'unknown_param': [], 'references': [], 'name': '', 'name_text': '', 'has_fusees': False, 'link': '', 'fusion': [{'references': [], 'fusees': []}]}
    evo_obj['type'] = evo_type
    if evo_type in ['digimon', 'non_digimon', 'any']:
        has_fusees = True
        # Split into primary evo and fusees by splitting at (with
        split_pos = evo_text.lower().find('with ')
        if split_pos == -1:
            split_pos = evo_text.lower().find('including ')
            if split_pos == -1:
                has_fusees = False
        if has_fusees:
            return evo_text
       

def get_evolutions(content:dict, digi_obj:dict, non_digi_obj:dict)->None:
    # E.g.
    # [[:Category:Adult Level|Any Adult]] or [[:Category:Armor Level|Any Armor Digimon]] (with the [[Human Spirit of Fire]]){{rfc|St|701}}"
    # Any [[Child]] [[:Category:Dragon's Roar|Dragon's Roar]] Digimon from [[Card Game Alpha]]{{rfc|Da|557}}
    # [[Digimon Card Game Colors and Levels#Red 2|Any Red Tamer from the ''Digimon Card Game'']]<ref name=DCG/>
    # [[DigiXros]] from [[Digimon Card Game DigiXros#Ancient Beatmon|certain Digimon from the ''Digimon Card Game'']]{{rfc|BT18|072 (DCG)}}
    # [[:Category:Perfect Level|Any Perfect Digimon]] belonging to either [[:Category:Metal Empire| Metal Empire]], or [[:Category:Nature Spirits|Nature Spirits]] with one of the [[Deva]]<ref name=D\u03b1-598>''[[D\u03b1-598]]''</ref>
    evo_map = {}
    # invalid_list = []
    session = requests.Session()
    count = 0
    for digimon in content:
        found_evo_from = False
        found_evo_to = False
        evo_map[digimon] = {}
        wikitext = wtp.parse(content[digimon]['wikitext'])
        sections = wikitext.get_sections()
        for section in sections:
            if section.title and section.title.strip().lower()=='evolves from':
                found_evo_from = True
                lists = section.get_lists()
                evo_map[digimon]['evolve_from'] = process_evo_list([item for list1 in lists for item in list1.items] if len(lists) else [], digi_obj, non_digi_obj, session)
                count += len(evo_map[digimon]['evolve_from'])
            if section.title and section.title.strip().lower()=='evolves to':
                found_evo_to = True
                lists = section.get_lists()
                evo_map[digimon]['evolve_to'] = process_evo_list([item for list1 in lists for item in list1.items]  if len(lists) else [], digi_obj, non_digi_obj, session)
                count += len(evo_map[digimon]['evolve_to'])
        if not found_evo_from:
            print(digimon,"did not have Evolves From section")
        if not found_evo_to:
            print(digimon,"did not have Evolves To section")
    # print(invalid_list)
    # print(Counter(invalid_list))
    # with open('evo_list_unknown.json', 'w') as file_out:
    #     json.dump(Counter(invalid_list), file_out)
    print(f'Evos: {count}')
    with open('evo_list_fusions.json', 'w') as file_out:
        json.dump(evo_map, file_out)

def get_patterns_for_fusion():
    content = {}
    with open('evo_list_fusions.json', 'r') as file_in:
        content = json.load(file_in)
    pattern_set = set()
    for digimon, data in content.items():
        if 'evolve_from' in data:
            for evo in data['evolve_from']:
                # pattern = re.search(r'\((.*?)\)',evo).group(1) # Getting text in paranthesis
                pattern = re.sub(r'\[\[.*?\]\]', 'X', evo) #Replacing all links with X
                pattern = wtp.parse(pattern).plain_text().strip()
                pattern_set.add(pattern)
        if 'evolve_to' in data:
            for evo in data['evolve_to']:
                # pattern = re.search(r'\((.*?)\)',evo).group(1) # Getting text in paranthesis
                pattern = re.sub(r'\[\[.*?\]\]', 'X', evo) #Replacing all links with X
                pattern = wtp.parse(pattern).plain_text().strip()
                pattern_set.add(pattern)
    sorted_arr =  sorted(pattern_set)
    print(len(sorted_arr))
    with open('fusion_patterns.json', 'w') as file_out:
        json.dump({'List': sorted_arr}, file_out)

# content = load_content_json()
# digi = load_json()
# non_digi = load_non_digi_content()

# get_evolutions(content, digi, non_digi)
get_patterns_for_fusion()
