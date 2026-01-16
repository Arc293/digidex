import requests
import re
import urllib.parse
import json
import sys, traceback
from datetime import datetime
from bs4 import BeautifulSoup
import wikitextparser as wtp
from collections import Counter
import unicodedata

wikimon_url = "https://wikimon.net"
wikimon_api_url = "https://wikimon.net/api.php"

def load_json():
    digimon_list = {}
    try:
        with open('digi_list.json') as infile:
            digimon_list = json.load(infile)
    except Exception:
        print("Exception in user code:")
        print("-"*60)
        traceback.print_exc(file=sys.stdout)
        print("-"*60)
    
    return digimon_list

def load_non_digi_content():
    content = {}
    try:
        with open('non_digimon_list.json') as infile:
            content = json.load(infile)
    except Exception:
        print("Exception in user code:")
        print("-"*60)
        traceback.print_exc(file=sys.stdout)
        print("-"*60)
    return content

def load_content_json():
    content = {}
    try:
        with open('wikimon_scrap.json') as infile:
            content = json.load(infile)
    except Exception:
        print("Exception in user code:")
        print("-"*60)
        traceback.print_exc(file=sys.stdout)
        print("-"*60)
    return content

def get_date(date_string):
    return datetime.fromisoformat(date_string) #09:45, 17 October 2022

def get_digimon_list_for_api_legacy(value_list=None):
    # Return titles param value for attribute in batches of 50
    digimon_list = load_json()
    urlfriendlyname_list = []
    all_titles = []
    if value_list == None:
        for name,body in digimon_list.items():
            urlfriendlyname_list.append(body["url"].replace(wikimon_url+"/",""))
            if len(urlfriendlyname_list) == 50:
                all_titles.append('|'.join(urlfriendlyname_list))
                urlfriendlyname_list.clear()
    else:
        for digimon in value_list:
            urlfriendlyname_list.append(digimon_list[digimon]["url"].replace(wikimon_url+"/",""))
            if len(urlfriendlyname_list) == 50:
                all_titles.append('|'.join(urlfriendlyname_list))
                urlfriendlyname_list.clear()
    if len(urlfriendlyname_list)>0:
        all_titles.append('|'.join(urlfriendlyname_list))
    return all_titles

def get_digimon_list_for_api(value_list):
    all_titles = []
    chunk_string_arr = []
    for digimon in value_list:
        chunk_string_arr.append(urllib.parse.quote(digimon))
        if len(chunk_string_arr) == 50:
            all_titles.append('|'.join(chunk_string_arr))
            chunk_string_arr.clear()
    if len(chunk_string_arr)>0:
        all_titles.append('|'.join(chunk_string_arr))
    return all_titles

def get_digimon_list(session=None):
    try:
        digimon_list = []
        if session == None:
            session = requests.Session()
        # Digimon from Category: Digimon
        params = 'action=query&format=json&list=categorymembers&cmpageid=6&cmlimit=500'
        continueparam = ''
        while True:
            response = session.get(url='https://wikimon.net/api.php',
                        params= params+continueparam).json()
            digimon_list.extend([digi['title'] for digi in response['query']['categorymembers'] 
                                if (digi['pageid'] not in [565, 58049, 5, 641, 38872]
                                and not digi['title'].startswith('Category:'))])
            if 'continue' in response:
                continueparam = f'&cmcontinue={response["continue"]["cmcontinue"]}'
            else:
                break
        # Unreleased digimon
        params = 'action=query&cmprop=title&format=json&list=categorymembers&cmpageid=686&cmlimit=500'
        continueparam = ''
        while True:
            response = session.get(url='https://wikimon.net/api.php',
                        params= params+continueparam).json()
            digimon_list.extend([digi['title'] for digi in response['query']['categorymembers'] ])
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
    return digimon_list

def get_absent_digimon(digi_obj, new_digimon_list):
    new_digimon_set = set(new_digimon_list)
    old_digimon_set = set(digi_obj.keys())
    deleted_set = old_digimon_set.difference(new_digimon_set)
    return(list(deleted_set))


def scrap_and_save_page_content():
    # digimon_list = load_json()
    page_object = {}
    digi_obj = {}
    try:
        with open('wikimon_scrap.json') as infile:
            page_object = json.load(infile)
    except Exception:
        print("Exception in user code:")
        print("-"*60)
        traceback.print_exc(file=sys.stdout)
        print("-"*60)
    try:
        with open('digi_list.json') as infile:
            digi_obj = json.load(infile)
    except Exception:
        print("Exception in user code:")
        print("-"*60)
        traceback.print_exc(file=sys.stdout)
        print("-"*60)

    changed = False
    last_update = None
    try:
        digimon_to_update = []
        session = requests.Session()
        digimon_list = get_digimon_list(session=session)
        absent_digimon = get_absent_digimon(digi_obj, digimon_list)
        if len(absent_digimon)>0:
            changed = True
            for del_digi in absent_digimon:
                if del_digi in page_object:
                    del page_object[del_digi]
                del digi_obj[del_digi]
                print(f'Entry for {del_digi} has been removed from wiki (redirected to other page)')
            with open('digi_list.json', 'w') as outfile:
                json.dump(digi_obj, outfile, sort_keys=True)
        # Get last revision timestamps from API
        for titles in get_digimon_list_for_api(value_list=digimon_list):
            # print(titles)
            
            params = f'action=query&prop=revisions&titles={titles}&rvslots=*&rvprop=timestamp&format=json'
            data = session.get(url='https://wikimon.net/api.php',
                            params= params)
            data_obj = data.json()
            pages = data_obj['query']['pages']

            for id,body in pages.items():
                last_update = body
                digimon = body['title']
                date = body['revisions'][0]['timestamp']
                if digimon not in page_object:
                    page_object[digimon] = {}
                    changed = True

                if 'revision_date' not in page_object[digimon] or get_date(page_object[digimon]['revision_date']) < get_date(date):
                    page_object[digimon]['revision_date'] = date
                    changed = True
                    print(f'Page for {digimon} has new updates on: {date}')
                    digimon_to_update.append(digimon)
                else:
                    # print(f'Page for {digimon} is already up-to-date')
                    if 'wikitext' not in page_object[digimon] or 'redirected_names' not in page_object[digimon]:
                        digimon_to_update.append(digimon)
        if not len(digimon_to_update):
            print("Everything is up-to-date!")
        for titles in get_digimon_list_for_api(digimon_to_update):
            params = f'action=query&prop=revisions&titles={titles}&rvslots=*&rvprop=content&format=json'
            data = session.get(url='https://wikimon.net/api.php',
                            params= params)
            data_obj = data.json()
            pages = data_obj['query']['pages']

            for id,body in pages.items():
                digimon = body['title']
                wikitext = body['revisions'][0]['slots']['main']['*']
                page_object[digimon]['wikitext'] = wikitext
                changed = True
                print("Page content added for: ",digimon)
        print(f'Number of pages updated: {len(digimon_to_update)}')
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
            with open('wikimon_scrap.json', 'w') as outfile:
                json.dump(page_object, outfile, sort_keys=True)

def resolve_redirects(session, content):
    redirected_digi = []
    original_names = {}
    
    for digimon, body in content.items():
        if 'redirected_names' not in body:
            body['redirected_names'] = []
        redirected_name = ''
        if body['wikitext'].strip().lower().startswith("#redirect"):
            digi = re.search(r'\[\[(.*?)\]\]', body['wikitext']).group(1)
            redirected_name = digi
            redirected_digi.append(digi)
            if digi not in original_names:
                original_names[digi] = []
            original_names[digi].append(digimon)

        if redirected_name and redirected_name not in body['redirected_names']:
            print(f'{digimon} has redirected name: {redirected_name}')
            body['redirected_names'].append(redirected_name)
    titles_list = []
    for i in range(0,len(redirected_digi), 50):
        titles_list.append('|'.join(redirected_digi[i:i+50]))

    for titles in titles_list:
        params = f'action=query&prop=revisions&titles={titles}&rvslots=*&rvprop=content&format=json'
        data = session.get(url='https://wikimon.net/api.php',
                        params= params)
        data_obj = data.json()
        pages = data_obj['query']['pages']
        for id,body in pages.items():
            wikitext = body['revisions'][0]['slots']['main']['*']
            for original_digi_name in original_names[body['title']]:
                content[original_digi_name]['wikitext'] = wikitext
                print("Redirected page content updated for: ",original_digi_name)
            i+=1
    return (content,len(redirected_digi)>0)

def main(scrap_description, scrap_stats):
    newDigi = []
    try:
        page = requests.get(wikimon_url+"/List_of_Digimon")
        soup = BeautifulSoup(page.content, 'html.parser')
        digimon_tables = soup.find_all('table', class_='wikitable')

        digimon_list = load_json()
        digimon_row_list = []

        for table in digimon_tables:
            digimon_row_list.extend(table.find_all('tr'))

        for digimon_row in digimon_row_list:
            # print(digimon_row)
            digimon = digimon_row.find_all('td')
            if len(digimon) == 0:
                continue
            name = digimon[0].find('a')['title'].strip()
            if name not in digimon_list:
                newDigi.append(name)
                url = digimon[0].find('a')['href']
                kanji = digimon[1].text.strip()
                debut_year = digimon[2].text.strip()
                debut = digimon[3].text.strip()
                digimon_list[name] = {}

                digimon_list[name]['url'] = wikimon_url+url
                digimon_list[name]['kanji'] = kanji
                digimon_list[name]['debut_year'] = debut_year
                digimon_list[name]['debut'] = debut

                # print(name, kanji, debut_year, debut, url)
            
            
            # digimon_list[name]['description'] = 
    except Exception:
        print("Exception in user code:")
        print("-"*60)
        traceback.print_exc(file=sys.stdout)
        print("-"*60) 
    finally:
        if len(newDigi) > 0:
            print(f'Added {len(newDigi)} new digimon')
            print(newDigi)
            with open('digi_list.json', 'w') as outfile:
                json.dump(digimon_list, outfile, sort_keys=True)
        else:
            print("No new digimon added")


    # Descriptions in priority order: pnDigimonRefBookMultiMorphContent1, pn1aBandaiGamesMultiMorphContent1 pMiscMultiMorphContent1

def scrapDescriptionsLegacy():

    digimon_list = load_json()

    limit = 20
    digimon_processed = 0
    digimon_desc_added = 0

    no_description = []

    for digimon, body in digimon_list.items():
        if 'description' not in body:
            # Scrap page and get description from first MultiMorphContent1
             page = requests.get(body['url'])
             soup = BeautifulSoup(page.content, 'html.parser')
             div_content = soup.find_all('div')
             flag = False
             for div in div_content:
                if 'id' in div.attrs:
                    if "MultiMorphContent1" in div['id'] and len(div.text.strip()) > 0:
                        body['description'] = div.text.strip().replace("⇨ Japanese","")
                        # print(body)
                        flag = True
                        digimon_desc_added += 1
                        break
             if not flag:
                print("No description found for ",digimon)
                no_description.append(digimon)
        digimon_processed += 1
        if digimon_processed % 100 == 0:
            print("Processed count", digimon_processed)
        # if digimon_processed > limit:
        #     break
    
    if digimon_desc_added > 0:
        print(f'Added descriptions for {digimon_desc_added} digimon')
        print("No description found for: ", no_description)
        with open('digi_list.json', 'w') as outfile:
            json.dump(digimon_list, outfile, sort_keys=True)
    else:
        print("No new digimon added")

def scrapDescriptions(digimon, content, digi_obj, debug=False):

    infoTemplate = get_info_template(content[digimon]['wikitext'])
    if not infoTemplate:
        return False
    found = False
    for args in infoTemplate.arguments:
        if 'pe' in args.name or args.name == 'e':
            if(debug):
                print(args)
            desc = replace_breaks(remove_refs(args.value))
            if digimon not in digi_obj:
                digi_obj[digimon] = {}
            digi_obj[digimon]['description'] = recursive_parse_template(desc)
            found = True
            jap_desc = ''
            if args.name == 'e':
                if infoTemplate.has_arg('un'):
                    digi_obj[digimon]['description_source'] = infoTemplate.get_arg('un').value.strip()
                elif infoTemplate.has_arg('p'):
                    digi_obj[digimon]['description_source'] = infoTemplate.get_arg('p').value.strip()
                if infoTemplate.has_arg('j'):
                    jap_desc = infoTemplate.get_arg('j').value
            else:
                descName = args.name
                sourceName = descName.replace('e', 'n')
                japName = descName.replace('e', 'j')
                if infoTemplate.has_arg(sourceName):
                    if '1a' in sourceName:
                        sourceName = descName.replace('e', 'un')
                    digi_obj[digimon]['description_source'] = infoTemplate.get_arg(sourceName).value.strip()
                if infoTemplate.has_arg(japName):
                    jap_desc = infoTemplate.get_arg(japName).value
            if jap_desc:
                digi_obj[digimon]['description_japanese'] = recursive_parse_template(replace_breaks(remove_refs(jap_desc)))
            break
    if not found:
        print(f'Description not found for {digimon}')
    return found

def scrapStats(digimon:str, content:dict, digi_obj:dict)->bool:
    infoTemplate = get_info_template(content[digimon]['wikitext'])
    if not infoTemplate:
        return False
    found = True
    # a<X>, a<X>ref -> Attribute
    attributes = scrap_stat_with_prefix(infoTemplate, 'a', 1)
    # c,cref -> Class type
    class_type = scrap_stat_with_prefix(infoTemplate, 'c', 0)
    class_type = class_type[0] if len(class_type) else {}
    # f(x), f(x)ref - Field
    fields = scrap_stat_with_prefix(infoTemplate, 'f', 1)
    # g(x), g(x)ref - Group
    groups = scrap_stat_with_prefix(infoTemplate, 'g', 1)
    # l(x), l(x)ref - Level
    levels = scrap_stat_with_prefix(infoTemplate, 'l', 1)
     # t(x), t(x)ref - Type
    type = scrap_stat_with_prefix(infoTemplate, 't', 1)
    # w(x), w(x)ref - Weight
    weight = scrap_stat_with_prefix(infoTemplate, 'w', 0)
    # wp,wp2,... -> Equipment image, wpd,wpd2(or wp2d),... -> Equipment name
    equipment = scrap_stat_with_prefix(infoTemplate, 'wp', 0)

    stats = {
        'attributes': attributes,
        'class_type':class_type,
        'fields':fields,
        'groups':groups,
        'levels':levels,
        'type':type,
        'weight':weight,
        'equipment':equipment
    }
    
    # ad -> Anime debut
    anime_debut = scrap_stat_with_prefix(infoTemplate, 'ad', 0)
    anime_debut = anime_debut[0]['value'] if len(anime_debut) else ''
    # cd -> Card debut
    card_debut = scrap_stat_with_prefix(infoTemplate, 'cd', 0)
    card_debut = card_debut[0]['value'] if len(card_debut) else ''
    # gd - Debut game
    game_debut = scrap_stat_with_prefix(infoTemplate, 'gd', 0)
    game_debut = game_debut[0]['value'] if len(game_debut) else ''
    # md - manga debut
    manga_debut = scrap_stat_with_prefix(infoTemplate, 'md', 0)
    manga_debut = manga_debut[0]['value'] if len(manga_debut) else ''
    # vd= Vpet debut
    vpet_debut = scrap_stat_with_prefix(infoTemplate, 'vd', 0)
    vpet_debut = vpet_debut[0]['value'] if len(vpet_debut) else ''
    # yd,ydr - Debut year, dy reference
    debut_year = scrap_stat_with_prefix(infoTemplate, 'yd', 0)
    debut_year = debut_year[0] if len(debut_year) else {}
    # drbed, drbedy - drb entry date, year
    ded = scrap_stat_with_prefix(infoTemplate, 'drbed', 0)
    dedy = scrap_stat_with_prefix(infoTemplate, 'drbedy', 0)
    drb_entry_date = {
        'date': ded[0]['value'] if len(ded) else '',
        'year': dedy[0]['value'] if len(dedy) else ''
    }

    debut = {
        "anime_debut": anime_debut,
        "card_debut": card_debut,
        "game_debut": game_debut,
        "manga_debut": manga_debut,
        "vpet_debut": vpet_debut,
        "debut_year": debut_year,
        "drb_entry_date": drb_entry_date
    }
   
    # aln<x>, aln<x>ref -> Title
    titles = scrap_stat_with_prefix(infoTemplate, 'aln', 1)
    # altn, altnref -> Other names
    other_names = scrap_stat_with_prefix(infoTemplate, 'altn', 0)
    other_names = other_names[0] if len(other_names) else {}
    # dub,dub2,dub3...dref,dref2 - dub names
    dub_names = scrap_stat_with_prefix(infoTemplate, 'dub', 0)
    # da,da2 - digialphabet name
    digimoji = scrap_digimoji(infoTemplate)
    # develn - development name
    development_name = scrap_stat_with_prefix(infoTemplate, 'develn', 0)
    development_name = development_name[0]['value'] if len(development_name) else ''
    # kan, kan2 - kanji
    kanji = [kanji['value'] for kanji in scrap_stat_with_prefix(infoTemplate, 'kan', 0)]
    # ol - other language
    ol = scrap_stat_with_prefix(infoTemplate, 'ol', 0)
    other_language = replace_breaks((ol[0]['value'] if len(ol) else ''))
    # rom - romaji
    romaji = scrap_stat_with_prefix(infoTemplate, 'rom', 0)
    romaji = romaji[0]['value'] if len(romaji) else ''

    alt_names = {
        "titles": titles,
        "other_names": other_names,
        "dub_names": dub_names,
        "digimoji": digimoji,
        "development_name": development_name,
        "kanji": kanji,
        "other_language": other_language,
        "romaji": romaji
    }
    
    # drbentry - {{DRBEntry}} template -> arg.value = drb number(s), tricky to parse
    # dsgn - Design and analysis
    design_and_analysis = scrap_stat_with_prefix(infoTemplate, 'dsgn', 0)
    design_and_analysis = design_and_analysis[0]['value'] if len(design_and_analysis) else ''
    # image, image2 - Image
    images = [image['value'].split('!')[0] for image in scrap_stat_with_prefix(infoTemplate, 'image', 0)]
    # s(x), s(x)ref - Subspecies
    subspecies = scrap_stat_with_prefix(infoTemplate, 's', 1)
     # name
    name = scrap_stat_with_prefix(infoTemplate, 'name', 0)
    name = name[0]['value'] if len(name) else digimon
     # code, com - ignore
    # d,q,io,d2ref,dlf,ed,featured,imagesize,ipa,it,n,nam,no,od,oj - ignore
    # q - Quote from tcg or anime

    stat_box = {
        "name": name,
        # "redirected_names": content[digimon]['redirected_names'],
        "images": images,
        "stats": stats,
        "debut": debut,
        "alt_names": alt_names,
        "subspecies": subspecies,
        "design_and_analysis": design_and_analysis
    }

    digi_obj[digimon].update(stat_box)

    # print(json.dumps(stat_box,indent=4))

def scrap_drb_index(content:dict, digi_obj:dict):
    all_digi = set()
    digi_with_index = set()
    index_map = {}
    old_digimon = []
    link_digi = {}
    for digimon in content:
        # print(digimon)
        all_digi.add(digimon)
        infoTemplate = get_info_template(content[digimon]['wikitext'])
        if infoTemplate:
            if infoTemplate.has_arg('drbentry'):
                drb_templates = wtp.parse(infoTemplate.get_arg('drbentry').value).templates
                if len(drb_templates):
                    drb_template = drb_templates[0]
                    if drb_template.name == 'DRBEntry':
                        if len(drb_template.arguments):
                            entry_numbers = extract_numbers_from_drbentry(get_all_non_named_arg(drb_template.arguments),digimon)
                            drb_digimon = extract_digimon_from_drbentry(drb_template)
                            drb_digimon.append(digimon)
                            entry_numbers.sort()
                            drb_digimon.sort()
                            if len(entry_numbers) != len(drb_digimon):
                                print(digimon,'numbers dont match..',len(entry_numbers), len(drb_digimon)+1)
                            else:
                                for i in range(0,len(entry_numbers)):
                                    if drb_digimon[i] in index_map:
                                        continue
                                    if drb_digimon[i] in digi_obj:
                                        index_map[drb_digimon[i]] = entry_numbers[i]
                                        digi_with_index.add(drb_digimon[i])
                        else:
                            old_digimon.append(digimon)
                            digi_with_index.add(digimon)         
                    # else:
                    #     print(digimon, 'does not have DRBEntry template 2')
                else:
                    raw_val = infoTemplate.get_arg('drbentry').value
                    if 'incorporated into' in raw_val:
                        digi_name = re.search(r'incorporated into (.*?)\'s profile', raw_val).group(1)
                        print('Link digi:', digi_name)
                        link_digi[digimon] = digi_name
                        digi_with_index.add(digimon)
    old_digimon.sort()
    for i in range(0,len(old_digimon)):
        index_map[old_digimon[i]] = i+1
    for links in link_digi:
        index_map[links] = index_map[link_digi[links]] + 0.1
    # print("Diff:",all_digi.difference(digi_with_index), len(all_digi.difference(digi_with_index)))

    for digimon in index_map:
        digi_obj[digimon]['drb_index'] = index_map[digimon]

def extract_numbers_from_drbentry(num_list:list,digimon:str)->list:
    nums = []
    for num_str in num_list:
        if num_str.isdigit():
            nums.append(int(num_str))
        else:
            nums_raw = num_str.split(',')
            for num_raw in nums_raw:
                a = num_raw.strip()
                if a.isdigit():
                    nums.append(int(a))
                else:
                    a = a.replace('th','').replace('st','').replace('nd','').replace('rd','')
                    if a.isdigit():
                        nums.append(int(a))
                    # else:
                    #     print(digimon,"error in number:", num_raw)
    return nums

def extract_digimon_from_drbentry(template:wtp.Template)->list:
    count = 2
    digimon = []
    while template.has_arg(str(count)+'a'):
        raw_val = template.get_arg(str(count)+'a').value
        if ' and ' in raw_val:
            digimon.extend([digi.strip() for digi in raw_val.split(' and ') if digi.strip()])
        else:
            digimon.extend([digi.strip() for digi in raw_val.split(',') if digi.strip()])
        count+=1
    return digimon

def translate_prefix(prefix:str)->str:
    match prefix:
        case 'a':
            return 'attribute'
        case 'ad':
            return 'anime_debut'
        case 'aln':
            return 'title'
        # altn, altnref -> Other names
        case 'altn':
            return 'alternate_names'
        # c,cref -> Class type
        case 'c':
            return 'class'
        # cd -> Card debut
        case 'cd':
            return 'card_debut'
        # code, com - ignore
        # d,q,io,d2ref,dlf,ed,featured,imagesize,ipa,it,n,nam,no,od,oj - ignore
        # da,da2 - digialphabet name
        case 'da':
            return 'digialphabet_names'
        # develn - development name
        case 'develn':
            return 'development_name'
        # drbed, drbedy - drb entry date, year
        case 'drbed':
            return 'drb_entry_date'
        # drbentry - {{DRBEntry}} template -> arg.value = drb number(s), tricky to parse
        case 'drbentry':
            return 'drb_index'
        # dub,dub2,dub3...dref,dref2 - dub names
        case 'dub':
            return 'dub_names'
        # dsgn - Design and analysis
        case 'dsgn':
            return 'design_and_analysis'
        # f(x), f(x)ref - Field
        case 'f':
            return 'field'
        # g(x), g(x)ref - Group
        case 'g':
            return 'group'
        # gd - Debut game
        case 'gd':
            return 'video_game_debut'
        # image, image2 - Image
        case 'image':
            return 'image_url'
        # kan, kan2 - kanji
        case 'kan':
            return 'kanji'
        # l(x), l(x)ref - Level
        case 'l':
            return 'level'
        # md - manga debut
        case 'md':
            return 'manga_debut'
        # name
        case 'name':
            return 'name'
        # ol - other language
        case 'ol':
            return 'other_language'
        # q - Quote from tcg or anime (ignore for now)
        case 'q':
            return 'quotes'
        # rom - romaji
        case 'rom':
            return 'romaji_name'
        # s(x), s(x)ref - Subspecies
        case 's':
            return 'subspecies'
        # t(x), t(x)ref - Type
        case 't':
            return 'type'
        # vd= Vpet debut
        case 'vd':
            return 'vpet_debut'
        # w(x), w(x)ref - Weight
        case 'w':
            return 'weight'
        # yd,ydr - Debut year, dy reference
        case 'yd':
            return 'debut_year'
        # wp,wp2,... -> Equipment image, wpd,wpd2(or wp2d),... -> Equipment name
        case 'wp':
            return 'equipment'
        

def get_arg_name_from_prefix(prefix:str, count:int)->str:
    if count == 0:
        return prefix
    else:
        return prefix+str(count)

def scrap_digimoji(infoTemplate:wtp.Template):
    digimoji = {}
    if infoTemplate.has_arg('da'):
        da = infoTemplate.get_arg('da')
        if len(wtp.parse(da.value).templates):
            da_temp = wtp.parse(da.value).templates[0]
            digimoji[da_temp.name] = [alph.value.strip() for alph in da_temp.arguments]
    if infoTemplate.has_arg('da2'):
        da = infoTemplate.get_arg('da2')
        if len(wtp.parse(da.value).templates):
            da_temp = wtp.parse(da.value).templates[0]
            digimoji[da_temp.name] = [alph.value.strip() for alph in da_temp.arguments]
    return digimoji

def scrap_single_stat(infoTemplate:wtp.Template, prefix:str)->str:
    stat = ''
    if infoTemplate.has_arg(get_arg_name_from_prefix(prefix,0)):
        arg = infoTemplate.get_arg(get_arg_name_from_prefix(prefix,0))
        stat = unicodedata.normalize('NFKC', recursive_parse_template(replace_breaks(arg.value.strip())))
    return stat

def scrap_stat_with_prefix(infoTemplate:wtp.Template, prefix:str, count:int)->list:
    stat_list = []
    while infoTemplate.has_arg(get_arg_name_from_prefix(prefix,count)):
        obj = {}
        base_arg = infoTemplate.get_arg(get_arg_name_from_prefix(prefix,count))
        if not base_arg.value.strip():
            if count > 0:
                count += 1
            else:
                count += 2
            continue
        obj['value'] = unicodedata.normalize('NFKC', recursive_parse_template(replace_breaks(base_arg.value.strip())))
        if prefix == 'dub':
            ref_arg = infoTemplate.get_arg('dref'+(str(count) if count>0 else ''))
        elif prefix == 'yd':
            ref_arg = infoTemplate.get_arg('ydr')
        elif prefix == 'wp':
            suffix = str(count) if count>0 else ''
            if infoTemplate.has_arg('wpd'+suffix):
                ref_arg = infoTemplate.get_arg('wpd'+suffix)
            else:
                ref_arg = infoTemplate.get_arg('wp'+suffix+'d')
        else:
            ref_arg = infoTemplate.get_arg(get_arg_name_from_prefix(prefix,count)+'ref')
        has_ref = False
        if ref_arg:          
            ref_template_list = wtp.parse(ref_arg.value).templates
            if ref_template_list:
                ref_temp = ref_template_list[0]
                obj['reference'] = recursive_parse_template(replace_breaks(ref_temp.string))    
                has_ref = True      
            else:
                arg = ref_arg.value
                ref1 = get_tag_property('ref','name',arg)
                ref2 = wtp.parse(arg).plain_text().strip()
                ref_name = ''
                if ref1:
                    ref_name+=ref1
                    if ref2:
                        ref_name+=f' ({ref2})'
                elif ref2:
                    ref_name = ref2
                if ref_name:
                    obj['reference'] = replace_breaks(ref_name)
                    has_ref = 'True'
        if not has_ref:
            obj['reference'] = ''
        stat_list.append(obj)
        if count > 0:
            count += 1
        else:
            count += 2
    return stat_list

def get_tag_property(tag:str, property:str, text:str)->str:
    soup = BeautifulSoup(text, 'lxml')
    tg = soup.find(tag)
    if not tg:
        # print(f'No {tag} in {text}')
        return ''
    if not tg.has_attr(property):
        # print(f'No {property} in {text}')
        return ''
    val = tg[property]
    if val.endswith('/'):
        val = val[0:-1]
    return val

def recursive_parse_template(content:str)->str:
    parsed_content = wtp.parse(content)
    while len(parsed_content.templates) > 0 or len(parsed_content.wikilinks) > 0 :
        content = parsed_content.plain_text(replace_templates= template_replacer)
        parsed_content = wtp.parse(content)
    return content.strip()

def get_info_template(wikitext: str)->wtp.Template:
    parsed = wtp.parse(wikitext)
    return next((x for x in parsed.templates if x.name.strip() == 'S2'), None)

def remove_refs(content:str)->str:
    soup = BeautifulSoup(content, 'lxml')
    for ref in soup.find_all('ref'):
        ref.decompose()
    return soup.text

def replace_breaks(content:str)->str:
    return content.replace('<br>', '\n').replace('<br/>', '\n')

def replace_ref_tag_with_template(content:str)->str:
    soup = BeautifulSoup(content, 'lxml')
    for ref in soup.find_all('ref'):
        ref_text = []
        
        if ref.string and ref.string.startswith('[['):
            ref_text.append(ref.string)
        elif ref.has_attr('name'):
            val = ref['name']
            if val.endswith('/'):
                val = val[0:-1]
            ref_text.append(val)
        ref.replace_with("{{ref|"+"|".join(ref_text)+"}}")
    return soup.text

def template_replacer(template: wtp.Template)->str:
    # print(template.name.lower(),template.pformat())
    match template.name.lower():
        case 'fc':
            return template.arguments[0].value
        case 'w'|'wikt':
            if len(template.arguments) == 1:
                return template.arguments[0].value
            else:
                return first_non_named_arg(template.arguments[1:])
        case 'at' | 'ato' | 'eq' | 'eqo':
            if len(template.arguments) == 1:
                return template.arguments[0].value
            filtered_list = get_all_non_named_arg(template.arguments)
            val = filtered_list[0] + ' ' + ' '.join([f'({val})' for val in filtered_list[1:]])
            return val
        case 'br':
            return '\n'
        case 'etyk'|'j'|'wikia'|'j2'|'url2':
            if len(template.arguments) == 1:
                return template.arguments[0].value
            else:
                return f'{template.arguments[1].value} ({template.arguments[0].value})'
        case 'fm'|'fmo'|'nn'|'nno':
            if len(template.arguments) == 1:
                return template.arguments[0].value
            else:
                return first_non_named_arg(template.arguments)
        case 'noprofile':
            if len(template.arguments) == 1:
                return f'No official description. Fanmade description:\n"{template.arguments[0].value}"'
            else:
                return 'No description found.'
        case 'note'|'s2ep':
            return ''
        case 'untranslated':
            return 'No English description found'
        case 'xab':
            return f'\nThe effect on {"/".join([t.value for t in template.arguments])}\'s Digicore due to the X-Antibody\n'
        case 'dd':
            return 'Digimon Reference Book'
        case 'dl':
            return 'Digimon Life'
        case 'ref':
            return wtp.parse(template.arguments[0].value).plain_text().strip()
        case 'rfc':
            return f'Card: {template.arguments[0].value}-{template.arguments[1].value}'
        case 'rfe':
            return f'Episode: {template.arguments[0].value}-{template.arguments[1].value} ({template.arguments[2].value})'
        case 'refd':
            return f'{template.arguments[0].value} (https://digimon.net/reference/detail.php?directory_name={template.arguments[1].value})'
        case 'dcdapmhl':
            return f'[{template.arguments[0].value.strip().upper()}]'
        case _:
            if len(template.arguments):
                return template.arguments[0].value
            else:
                return template.name
            
def parse_ref_tag(arg):
    ref1 = get_tag_property('ref','name',arg)
    ref2 = recursive_parse_template(arg)
    ref_name = ''
    if ref1:
        ref_name+=ref1
        if ref2:
            ref_name+=f' ({ref2})'
    elif ref2:
        ref_name = ref2
    return ref_name
  

def first_non_named_arg(arguments: list) -> str:
    for a in arguments:
        if a.name.isdigit():
            return a.value
def get_all_non_named_arg(arguments: list) -> list:
    val = []
    for a in arguments:
        if a.name.isdigit():
            val.append(a.value)
    return val
def print_digimon_list():
    digimon_list = load_json()

    for digimon in digimon_list:
        print(digimon)

def parse_content():
    data = requests.get(url='https://wikimon.net/api.php',
                        params= {
                            'action': 'query',
                            'prop': 'revisions',
                            'titles': 'Agumon',
                            'rvslots': '*',
                            'rvprop': 'content',
                            'format': 'json'
                        })
    data_obj = data.json()
    pages = data_obj['query']['pages']

    for id,body in pages.items():
        wikitext = body['revisions'][0]['slots']['main']['*']
        parsed = wtp.parse(wikitext)
        sections = parsed.get_sections(top_levels_only=True, include_subsections=True)

        # for section in sections:
        #     print(len(section.sections))
        # print("Length = ",len(sections))
        templates = parsed.templates
        count = 1
        for template in templates:
            print(f'{count} {template.name} =====================')
            for arguments in template.arguments:
                print(arguments.name, arguments.value)
            count += 1
        print(len(templates))

def compare_keys():
    digimon_list = load_json()
    page_object = {}
    try:
        with open('wikimon_scrap.json') as infile:
            page_object = json.load(infile)
    except Exception:
        print("Exception in user code:")
        print("-"*60)
        traceback.print_exc(file=sys.stdout)
        print("-"*60)
    
    for key1 in digimon_list:
        if key1 not in page_object:
            print(key1)
    print("="*10)
    for key1 in page_object:
        if key1 not in digimon_list:
            print(key1)

# Original evo parser
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

            if section.title and section.title.strip().lower()=='evolves to':
                found_evo_to = True
                lists = section.get_lists()
                evo_map[digimon]['evolve_to'] = process_evo_list([item for list1 in lists for item in list1.items]  if len(lists) else [], digi_obj, non_digi_obj, session)
        if not found_evo_from:
            print(digimon,"did not have Evolves From section")
        if not found_evo_to:
            print(digimon,"did not have Evolves To section")
    # print(invalid_list)
    # print(Counter(invalid_list))
    # with open('evo_list_unknown.json', 'w') as file_out:
    #     json.dump(Counter(invalid_list), file_out)
    with open('evo_list_2.json', 'w') as file_out:
        json.dump(evo_map, file_out)

# Only fetches the evo text in list, will use it for LLM analysis
def get_evolutions_text_only(content:dict, digi_obj:dict, non_digi_obj:dict)->None:
    # E.g.
    # [[:Category:Adult Level|Any Adult]] or [[:Category:Armor Level|Any Armor Digimon]] (with the [[Human Spirit of Fire]]){{rfc|St|701}}"
    # Any [[Child]] [[:Category:Dragon's Roar|Dragon's Roar]] Digimon from [[Card Game Alpha]]{{rfc|Da|557}}
    # [[Digimon Card Game Colors and Levels#Red 2|Any Red Tamer from the ''Digimon Card Game'']]<ref name=DCG/>
    # [[DigiXros]] from [[Digimon Card Game DigiXros#Ancient Beatmon|certain Digimon from the ''Digimon Card Game'']]{{rfc|BT18|072 (DCG)}}
    # [[:Category:Perfect Level|Any Perfect Digimon]] belonging to either [[:Category:Metal Empire| Metal Empire]], or [[:Category:Nature Spirits|Nature Spirits]] with one of the [[Deva]]<ref name=D\u03b1-598>''[[D\u03b1-598]]''</ref>

    # invalid_list = []
    session = requests.Session()
    for digimon in content:
        found_evo_from = False
        found_evo_to = False
        if digimon not in digi_obj:
            digi_obj[digimon] = {}
        wikitext = wtp.parse(content[digimon]['wikitext'])
        sections = wikitext.get_sections()
        for section in sections:
            if section.title and section.title.strip().lower()=='evolves from':
                found_evo_from = True
                lists = section.get_lists()
                digi_obj[digimon]['evolve_from'] = process_evo_list_simple([item for list1 in lists for item in list1.items] if len(lists) else [], digi_obj, non_digi_obj, session)
            if section.title and section.title.strip().lower()=='evolves to':
                found_evo_to = True
                lists = section.get_lists()
                digi_obj[digimon]['evolve_to'] = process_evo_list_simple([item for list1 in lists for item in list1.items]  if len(lists) else [], digi_obj, non_digi_obj, session)
        if not found_evo_from:
            print(digimon,"did not have Evolves From section")
        if not found_evo_to:
            print(digimon,"did not have Evolves To section")
    # for non_digimon in non_digi_obj:
    #     digi_obj[non_digimon] = {}
def flatten(xss):
    return [x for xs in xss for x in xs]
def find_and_resolve_all_evo_links(content:dict, digi_obj:dict)->None:
    evo_keys = set()
    session = requests.Session()
    redirected_names_list = flatten([x['redirected_names'] for x in digi_obj.values() if 'redirected_names' in x])
    print(redirected_names_list)
    for digimon in content: 
        wikitext = wtp.parse(content[digimon]['wikitext'])
        sections = wikitext.get_sections()
        
        for section in sections:
            if section.title and (section.title.strip().lower()=='evolves from' or section.title.strip().lower()=='evolves to'):
                lists = section.get_lists()
                evo_list = [item for list1 in lists for item in list1.items] if len(lists) else []
                # print('Unknown keys', get_unknown_keys(evo_list, digi_obj))
                evo_keys.update(get_unknown_keys(evo_list, digi_obj, redirected_names_list))
    digi_obj_changed = False
    other_obj_changed = False
    other_obj = load_non_digi_content()
    for titles in get_digimon_list_for_api(value_list=evo_keys):

        params = f'action=query&prop=revisions&titles={titles}&rvslots=*&rvprop=content&format=json'
        data = session.get(url='https://wikimon.net/api.php',
                        params= params)
        data_obj = data.json()
        normalised_list = data_obj['query']['normalized'] if 'normalized' in data_obj['query'] else []
        for normalised in normalised_list:
            if normalised['to'] in digi_obj:
                if 'redirected_names' not in digi_obj[normalised['to']]:
                    digi_obj[normalised['to']]['redirected_names'] = []
                digi_obj[normalised['to']]['redirected_names'].append(normalised['from'])
                print('Normalised redirected name added:',normalised['from'], normalised['to'])

        pages = data_obj['query']['pages']
        
        for id,body in pages.items():
            title = body['title']
            # print(title)
            if 'missing' in body: # Page is missing
                print(title,': page missing')
                if not title in other_obj:
                    other_obj[title] = {}
                other_obj[title]['wikitext'] = ''
                continue
            wikitext = body['revisions'][0]['slots']['main']['*']

            if wikitext.strip().lower().startswith("#redirect"):
                redirected_title = re.search(r'\[\[(.*?)\]\]', wikitext).group(1)
                if redirected_title in digi_obj and 'redirected_names' not in digi_obj[redirected_title]:
                    digi_obj[redirected_title]['redirected_names'] = []
                if redirected_title in digi_obj and title not in digi_obj[redirected_title]['redirected_names']:
                    digi_obj[redirected_title]['redirected_names'].append(title)
                    print('New redirected name,',title,',found for',redirected_title)
                    digi_obj_changed = True
                elif redirected_title not in digi_obj and title not in other_obj:
                    other_obj[title] = {}
                    other_obj[title]['wikitext'] = wikitext
                    other_obj_changed = True
                    print('Unknown redirect for', title, redirected_title)
            elif title not in other_obj:
                other_obj[title] = {}
                other_obj[title]['wikitext'] = wikitext
                other_obj_changed = True
                print('Added page content for non-digimon page: ',title)
    other_obj, redirect_changed = resolve_redirects(session, other_obj)
    # if(digi_obj_changed):
    #     with open('digi_list.json', 'w') as file_out:
    #         json.dump(digi_obj, file_out, sort_keys=True)   
    if(other_obj_changed or redirect_changed):
        with open('non_digimon_list.json', 'w') as file_out:
            json.dump(other_obj, file_out, sort_keys=True)  
                
def check_wikilink_is_reference(link:wtp.WikiLink):
    if link.parent(type_='Template') and wtp.Template(link.parent(type_='Template').string).name in ('ref', 'rfc', 'rfe', 'refd'):
        return True
    else:
        return False
def get_unknown_keys(evo_list:list, digi_obj:dict, redirected_names:list)->list:
    keys = []
    for evo in evo_list:
        evo = evo.replace("'''", "").replace("''","").replace("\u200e","")
        evo = remove_refs(evo)
        evo_parse = wtp.parse(evo)
        if evo_parse.plain_text().strip().startswith('Any'):
            continue
        if evo_parse.wikilinks:
            for link in evo_parse.wikilinks:
                if check_wikilink_is_reference(link):
                    continue
                evo_title = link.title
                if not(evo_title in digi_obj or evo_title in redirected_names or evo_title.lower()=="digitama" or evo_title.lower()=="digixros" or 'Category' in evo_title):
                    keys.append(evo_title)
    return keys

def process_evo_list(evo_list:list,digi_obj:dict, non_digi_obj:dict, session:requests.Session)->list:
    prc_list = []
    for evo in evo_list:
        evo_obj = {}
        # If starts with ''', should mark as important
        evo_obj['major'] = evo.startswith("'''")
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
                
                elif \
                evo_title == 'Digimon Card Game Colors and Levels' or\
                evo_title == 'Digimon World: Digital Card Arena Attributes and Levels' or\
                evo_title == 'Digimon World: Digital Card Battle Attributes and Levels' or\
                evo_title == 'Battle Spirits Card Game Colors and Levels' or\
                evo_title == 'Digimon Card Game DigiXros'  :
                    evo_obj = process_evo(evo, 'card', digi_obj, non_digi_obj)

                
                elif evo_parse.plain_text().strip().startswith('Any'):
                    evo_obj = process_evo(evo, 'any', digi_obj, non_digi_obj)
                elif evo_title.lower()=="digitama":
                    evo_obj = process_evo(evo, 'egg', digi_obj, non_digi_obj)
                elif evo_title.lower()=="digixros":
                    evo_obj = process_evo(evo, 'xros', digi_obj, non_digi_obj)
                elif deep_search_non_digi(evo_title, non_digi_obj):
                    evo_obj = process_evo(evo, 'non_digimon', digi_obj, non_digi_obj)
                else:
                    evo_obj = process_evo(evo, 'text', digi_obj, non_digi_obj)
            else:
                process_evo(evo, 'text', digi_obj, non_digi_obj)
        else:
            evo_obj = process_evo(evo, 'text', digi_obj, non_digi_obj)
        prc_list.append(evo_obj)
    return prc_list

def process_evo_list_simple(evo_list:list,digi_obj:dict, non_digi_obj:dict, session:requests.Session)->list:
    prc_list = []
    for evo in evo_list:
        evo_obj = {}
        # If starts with ''', should mark as important
        evo_obj['major'] = evo.startswith("'''")
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
                    evo_obj = process_evo_simple(evo, 'digimon', digi_obj, non_digi_obj)
                # elif re.search("^any.*from.*card.*", evo_name.lower()):
                #     evo_obj['valid_card'] = evo
                
                elif \
                evo_title == 'Digimon Card Game Colors and Levels' or\
                evo_title == 'Digimon World: Digital Card Arena Attributes and Levels' or\
                evo_title == 'Digimon World: Digital Card Battle Attributes and Levels' or\
                evo_title == 'Battle Spirits Card Game Colors and Levels' or\
                evo_title == 'Digimon Card Game DigiXros'  :
                    evo_obj = process_evo_simple(evo, 'card', digi_obj, non_digi_obj)

                
                elif evo_parse.plain_text().strip().startswith('Any'):
                    evo_obj = process_evo_simple(evo, 'any', digi_obj, non_digi_obj)
                elif evo_title.lower()=="digitama":
                    evo_obj = process_evo_simple(evo, 'egg', digi_obj, non_digi_obj)
                elif evo_title.lower()=="digixros":
                    evo_obj = process_evo_simple(evo, 'xros', digi_obj, non_digi_obj)
                elif deep_search_non_digi(evo_title, non_digi_obj):
                    evo_obj = process_evo_simple(evo, 'non_digimon', digi_obj, non_digi_obj)
                else:
                    evo_obj = process_evo_simple(evo, 'text', digi_obj, non_digi_obj)
            else:
                process_evo_simple(evo, 'text', digi_obj, non_digi_obj)
        else:
            evo_obj = process_evo_simple(evo, 'text', digi_obj, non_digi_obj)
        prc_list.append(evo_obj)
    return prc_list

def deep_search_digi(name, digi_obj):
    for keyname,digi in digi_obj.items():
        # print(keyname)
        if not 'name' in digi:
            continue
        if ('redirected_names' in digi and name in digi['redirected_names']) or name == digi['name'] or (digi['alt_names']['other_names'] and name == digi['alt_names']['other_names']['value']):
            return True, keyname
        elif len([dub['value'] for dub in digi['alt_names']['dub_names'] if dub['value'].lower() == name.lower()]):
            return True, keyname
    return False, None

def deep_search_non_digi(name, non_digi_obj):
    if name in non_digi_obj:
        return True, name
    for keyname,digi in non_digi_obj.items():        
        if name in digi['redirected_names']:
            return True, keyname
    return False, None

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
            evo_raw, fusees_raw = evo_text[:split_pos], evo_text[split_pos:]
        else:
            evo_raw = evo_text
        evo_obj['has_fusees'] = has_fusees
        # Process primary evo
        evo_parse = wtp.parse(replace_ref_tag_with_template(evo_raw))
        for link in evo_parse.wikilinks:
            if not check_wikilink_is_reference(link):
                if evo_type == 'digimon':
                    if link.title in digi_obj:
                        evo_obj['name'] = link.title
                    elif deep_search_digi(link.title, digi_obj)[0]:
                        evo_obj['name'] = deep_search_digi(link.title, digi_obj)[1]
                    elif link.title.lower() == 'evolution':
                        evo_obj['is_special_evo'] = True
                        evo_obj['special_evo_type'] = link.text
                    else:
                        evo_obj['unknown_param'].append(link.title)
                elif evo_type == 'non_digimon':

                    if deep_search_non_digi(link.title, non_digi_obj)[0]:
                        evo_obj['name'] = deep_search_non_digi(link.title, non_digi_obj)[1]
                        evo_obj['name_text'] = link.text.strip() if link.text else ''
                    else:
                        evo_obj['unknown_param'].append(link.title)
                elif evo_type == 'any':
                    evo_obj['name_text'] = link.text.strip() if link.text else ''
            else:
                evo_obj['references'].append(link.title)
        # Process fusees
        if has_fusees:
            split_fusee_text = fusees_raw.split('or ')
            evo_obj['fusion'] = []
            for fusee_text in split_fusee_text:
                fusee_obj = {'references': [], 'fusees': []}
                fusee_parse = wtp.parse(replace_ref_tag_with_template(fusee_text))

                if fusee_parse.wikilinks:
                    for link in fusee_parse.wikilinks:
                        if not check_wikilink_is_reference(link):
                            per_fusee_obj = {}
                            if link.title in digi_obj:
                                per_fusee_obj['name'] = link.title
                                per_fusee_obj['type'] = 'digimon'
                            elif deep_search_digi(link.title, digi_obj)[0]:
                                per_fusee_obj['name'] = deep_search_digi(link.title, digi_obj)[1]
                                per_fusee_obj['type'] = 'digimon'
                            elif deep_search_non_digi(link.title, non_digi_obj)[0]:
                                per_fusee_obj['name'] = deep_search_non_digi(link.title, non_digi_obj)[1]
                                per_fusee_obj['name_text'] = link.text.strip() if link.text else ''
                                per_fusee_obj['type'] = 'non_digimon'
                            else:
                                per_fusee_obj['name_text'] = link.text.strip() if link.text else ''
                                per_fusee_obj['type'] = 'unknown'
                            fusee_obj['fusees'].append(per_fusee_obj)
                        else:
                            fusee_obj['references'].append(link.title)
                evo_obj['fusion'].append(fusee_obj)
        # Check for rfc templates
        for template in wtp.parse(evo_text).templates:
            if template.name == 'rfc':
                if len(template.arguments) == 2:
                    evo_obj['references'].append(f'Card: {template.arguments[0].value}-{template.arguments[1].value}')
                elif len(template.arguments) == 1:
                    evo_obj['references'].append(f'Card: {template.arguments[0].value}')
    else:
        if evo_type == 'egg' or evo_type == 'xros':
            for template in wtp.parse(evo_text).templates:
                evo_obj['references'].append(template.plain_text(replace_templates=template_replacer))
        elif evo_type == 'text':
            evo_obj['name_text'] = wtp.parse(evo_text).plain_text(replace_templates=template_replacer)
        elif evo_type == 'card':
            card_link = wtp.parse(evo_text).wikilinks[0]
            evo_obj['name_text'] = card_link.text
            evo_obj['link'] = card_link.target
            for template in wtp.parse(evo_text).templates:
                if template.name == 'rfc':
                    if len(template.arguments) == 2:
                        evo_obj['references'].append(f'{template.arguments[0].value}-{template.arguments[1].value}')
                    elif len(template.arguments) == 1:
                        evo_obj['references'].append(f'{template.arguments[0].value}')
    return evo_obj    

def process_evo_simple(evo_text:str, evo_type:str, digi_obj:dict, non_digi_obj:dict):
    evo_obj = {'is_special_evo':False, 'special_evo_type': '', 'unknown_param': [], 'references': [], 'name': '', 'name_text': '', 'has_fusees': False, 'link': '', 'conditions': ''}
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
            evo_raw, fusees_raw = evo_text[:split_pos], evo_text[split_pos:]
        else:
            evo_raw = evo_text
        evo_obj['has_fusees'] = has_fusees
        # Process primary evo
        evo_parse = wtp.parse(replace_ref_tag_with_template(evo_raw))
        for link in evo_parse.wikilinks:
            if not check_wikilink_is_reference(link):
                if evo_type == 'digimon':
                    if link.title in digi_obj:
                        evo_obj['name'] = link.title
                    elif deep_search_digi(link.title, digi_obj)[0]:
                        evo_obj['name'] = deep_search_digi(link.title, digi_obj)[1]
                    elif link.title.lower() == 'evolution':
                        evo_obj['is_special_evo'] = True
                        evo_obj['special_evo_type'] = link.text
                    else:
                        evo_obj['unknown_param'].append(link.title)
                elif evo_type == 'non_digimon':

                    if deep_search_non_digi(link.title, non_digi_obj)[0]:
                        evo_obj['name'] = deep_search_non_digi(link.title, non_digi_obj)[1]
                        evo_obj['name_text'] = link.text.strip() if link.text else ''
                    else:
                        evo_obj['unknown_param'].append(link.title)
                elif evo_type == 'any':
                    evo_obj['name_text'] = link.text.strip() if link.text else ''
            else:
                evo_obj['references'].append(link.title)
        # Process fusees
        if has_fusees:
            condition_parse = wtp.parse(replace_ref_tag_with_template(fusees_raw))
            evo_obj['conditions']=condition_parse.plain_text(replace_wikilinks=False,replace_templates=template_replacer_refs)
            # split_fusee_text = fusees_raw.split('or ')
            # evo_obj['fusion'] = []
            # for fusee_text in split_fusee_text:
            #     fusee_obj = {'references': [], 'fusees': []}
            #     fusee_parse = wtp.parse(replace_ref_tag_with_template(fusee_text))

            #     if fusee_parse.wikilinks:
            #         for link in fusee_parse.wikilinks:
            #             if not check_wikilink_is_reference(link):
            #                 per_fusee_obj = {}
            #                 if link.title in digi_obj:
            #                     per_fusee_obj['name'] = link.title
            #                     per_fusee_obj['type'] = 'digimon'
            #                 elif deep_search_digi(link.title, digi_obj)[0]:
            #                     per_fusee_obj['name'] = deep_search_digi(link.title, digi_obj)[1]
            #                     per_fusee_obj['type'] = 'digimon'
            #                 elif deep_search_non_digi(link.title, non_digi_obj)[0]:
            #                     per_fusee_obj['name'] = deep_search_non_digi(link.title, non_digi_obj)[1]
            #                     per_fusee_obj['name_text'] = link.text.strip() if link.text else ''
            #                     per_fusee_obj['type'] = 'non_digimon'
            #                 else:
            #                     per_fusee_obj['name_text'] = link.text.strip() if link.text else ''
            #                     per_fusee_obj['type'] = 'unknown'
            #                 fusee_obj['fusees'].append(per_fusee_obj)
            #             else:
            #                 fusee_obj['references'].append(link.title)
            #     evo_obj['fusion'].append(fusee_obj)
        # Check for rfc templates
        for template in wtp.parse(evo_text).templates:
            if template.name == 'rfc':
                if len(template.arguments) == 2:
                    evo_obj['references'].append(f'Card: {template.arguments[0].value}-{template.arguments[1].value}')
                elif len(template.arguments) == 1:
                    evo_obj['references'].append(f'Card: {template.arguments[0].value}')
    else:
        if evo_type == 'egg' or evo_type == 'xros':
            for template in wtp.parse(evo_text).templates:
                evo_obj['references'].append(template.plain_text(replace_templates=template_replacer))
        elif evo_type == 'text':
            evo_obj['name_text'] = wtp.parse(evo_text).plain_text(replace_templates=template_replacer)
        elif evo_type == 'card':
            card_link = wtp.parse(evo_text).wikilinks[0]
            evo_obj['name_text'] = card_link.text
            evo_obj['link'] = card_link.target
            for template in wtp.parse(evo_text).templates:
                if template.name == 'rfc':
                    if len(template.arguments) == 2:
                        evo_obj['references'].append(f'{template.arguments[0].value}-{template.arguments[1].value}')
                    elif len(template.arguments) == 1:
                        evo_obj['references'].append(f'{template.arguments[0].value}')
    return evo_obj

def template_replacer_refs(template: wtp.Template)->str:
    # print(template.name.lower(),template.pformat())
    match template.name.lower():
        case 'ref':
            return f' ({wtp.parse(template.arguments[0].value).plain_text().strip()})'
        case 'rfc':
            return f' (Card: {template.arguments[0].value}-{template.arguments[1].value})'
        case 'rfe':
            return f' (Episode: {template.arguments[0].value}-{template.arguments[1].value} ({template.arguments[2].value}))'
        case 'refd':
            return f' ({template.arguments[0].value} (https://digimon.net/reference/detail.php?directory_name={template.arguments[1].value}))'
        case _:
            if len(template.arguments):
                return template.arguments[0].value
            else:
                return template.name
                  
def pretty_print(digimon: str, content: dict)-> None:
    print(get_info_template(content[digimon]['wikitext']).pformat())

def get_gallery_images(content, digimon, digi_obj):
    wikitext = wtp.parse(content[digimon]['wikitext'])
    if digimon not in digi_obj:
        digi_obj[digimon] = {}
    image_list = []
    for template in wikitext.templates:
        if template.name.strip() == 'IG' and len(template.arguments):
            
            images = scrap_stat_with_prefix(template, 'i', 1)
            for i in range(1,len(images)+1):
                images[i-1]['caption'] = recursive_parse_template(replace_breaks(template.get_arg(f'c{i}').value.strip())) if template.has_arg(f'c{i}') else ''
            image_list.extend([{'image': (images[x]['value'].split('<')[0]).split('!')[0], 'caption': images[x]['caption'].strip().replace('\n', ' ')} for x in range(0,len(images))])
    digi_obj[digimon]['image_gallery'] = image_list
    # sections = wikitext.get_sections()
    # for section in sections:
    #     # print(section.title)
    #     if section.title and section.title.lower().strip() in ['image gallery', 'virtual pets']:
    #         print(section.pformat())
    #         if len(section.templates):
    #             ig_template = section.templates[0]
    #             print(ig_template.name)
    #             if ig_template.name.strip() == 'IG' and len(ig_template.arguments):
    #                 print(ig_template.arguments)
            # lists = section.get_lists()
            # print(lists)
def get_tcg(content, digimon, session=None):
    if not session:
        session = requests.Session()
    wikitext = wtp.parse(content[digimon]['wikitext'])
    for template in wikitext.templates:
        if template.name.strip() == 'NeoTCG' and len(template.arguments):
            template_string = template.string.replace('\n','')
            params = f'action=expandtemplates&prop=wikitext&text={template_string}&title={digimon}&format=json'
            print(params)
            data = session.get(url='https://wikimon.net/api.php',
                            params= params)
            html_txt = data.json()['expandtemplates']['wikitext']
            soup = BeautifulSoup(html_txt, 'lxml')
            for i in range(1,len(template.arguments)+1):
                card_format = soup.find(id=f'TCGLink{i}').text
                print(f'===={card_format}====')
                cards = soup.find(id=f'TCGContent{i}').text
                images = [link.target for link in wtp.parse(cards).wikilinks if link.title.startswith('Image')]
                print(images)
            # try:
            #     with open('tcg_out_2.html',"w") as outfile:
            #         outfile.write(data_obj['expandtemplates']['wikitext'])
            # except Exception:
            #     print("Exception in user code:")
            #     print("-"*60)
            #     traceback.print_exc(file=sys.stdout)
            #     print("-"*60)
            # print(wtp.parse(data_obj['expandtemplates']['wikitext']).pformat())

def sort_in_drb_order():
    digi_obj = load_json()
    no_index_count = 0
    for key in digi_obj.keys():
        if 'name' not in digi_obj[key]:
            digi_obj[key]['name'] = key
        if 'drb_index' not in digi_obj[key]:
            digi_obj[key]['drb_index'] = -1
            no_index_count += 1
    digi_list = list(digi_obj.values())
    # print(digi_list)
    digi_list.sort(key=lambda x:x['drb_index'])
    with open('drb_order.txt', 'w') as outfile:
        for x in digi_list:
            outfile.write(f'{x['drb_index']} {x['name']}\n')
        outfile.write(f'Digimon count with no index = {no_index_count}')
# print(get_digimon_list_for_api())

# resolve_redirects(requests.Session(), load_content_json())
# main(None, None)
# print_digimon_list()
# parse_content()
# compare_keys()



# Scraping descriptions
# for digimon in content:
#     scrapDescriptions(digimon, content, digi_obj)

# with open('digi_descriptions.json', 'w') as outfile:
#     json.dump(digi_obj, outfile, sort_keys=True)

# pretty_print('Holy Angemon', content)
# get_digimon_list()

# Main section starts here
scrap_and_save_page_content()
compare_keys()
content = load_content_json()
digi_obj = load_json()
non_digi_obj = load_non_digi_content()
evo_obj = {}
last_digimon_updated = ''
try:
    for digimon in content:
        last_digimon_updated = digimon
        scrapDescriptions(digimon, content, digi_obj)
        scrapStats(digimon, content, digi_obj)
        get_gallery_images(content, digimon, digi_obj)
        
    find_and_resolve_all_evo_links(content, digi_obj)
    scrap_drb_index(content, digi_obj)
    get_evolutions_text_only(content,digi_obj, non_digi_obj)
    
except Exception:
        print("Exception in user code:")
        print("-"*60)
        traceback.print_exc(file=sys.stdout)
        print(f'Last digimon updated: {last_digimon_updated}')
        print("-"*60) 
finally:
    # split_dict = {}
    # count = 0
    # for key, value in evo_obj.items():
    #     split_dict[key] = value
    #     count += 1
    #     if count % 100 == 0:
    #          with open(f'evo_json_splits/evo_list_{count/100}.json', 'w') as outfile:
    #             json.dump(split_dict, outfile, sort_keys=True)
    #          split_dict = {}
    # with open(f'evo_json_splits/evo_list_{(count/100)+1}.json', 'w') as outfile:
    #         json.dump(split_dict, outfile, sort_keys=True)
    # print(count)
    with open('digi_list.json', 'w') as outfile:
        json.dump(digi_obj, outfile, sort_keys=True)
   

# Main section ends here

# get_absent_digimon(digi_obj)

# sort_in_drb_order()
# get_evolutions(content,digi_obj, non_digi_obj)

# scrapStats('Agumon', content, digi_obj)


