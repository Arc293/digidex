import requests
import re
import urllib.parse
import json
import sys, traceback
from clint.textui import progress
import wikitextparser as wtp
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
from tqdm import tqdm
from PIL import Image
from io import BytesIO

NO_IMG_URL = "https://wikimon.net/images/6/61/Digimon_noimage.jpg"

def get_image_list_for_api(value_list):
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

def get_image_list(digi_obj:dict, img_obj:dict, refresh_all:bool)->list:
    image_set = set()
    for digi_data in digi_obj.values():
        if 'images' in digi_data:
            image_set.update([f"Image:{image.split('!')[0]}" for image in digi_data['images'] if refresh_all or image.split('!')[0] not in img_obj])
        if 'image_gallery' in digi_data:
            image_set.update([f"Image:{image['image']}" for image in digi_data['image_gallery'] if refresh_all or image['image'] not in img_obj])
    return list(image_set)

def get_images_of_digimon(digimon: str, digi_obj:dict)->list:
    image_set = set()
    digi_data = digi_obj[digimon]
    if 'images' in digi_data:
        image_set.update([image.split('!')[0] for image in digi_data['images']])
    if 'image_gallery' in digi_data:
        image_set.update([image['image'] for image in digi_data['image_gallery']])
    return list(image_set)


def scrap_image_urls(refresh_all=False):
    # digimon_list = load_json()
    image_object = {}
    digi_obj = {}
    try:
        with open('image_urls.json') as infile:
            image_object = json.load(infile)
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
    last_update = None
    changed = False
    try:
        
        session = requests.Session()
        image_list = get_image_list(digi_obj, image_object, refresh_all)
        print(len(image_list))
        # Get last revision timestamps from API
        for titles in get_image_list_for_api(value_list=image_list):
             # print(titles)
            
            params = f'action=query&prop=imageinfo&titles={titles}&iiprop=url&format=json'
            data = session.get(url='https://wikimon.net/api.php',
                            params= params)
            data_obj = data.json()
            pages = data_obj['query']['pages']
            normalised_names = {}
            normalise_response = data_obj['query']['normalized']

            if normalise_response and len(normalise_response)>0:
                for response in normalise_response:
                    normalised_names[response['to']] = response['from']

            for id,body in pages.items():
                name = normalised_names[body['title']] if body['title'] in normalised_names else body['title']
                name = name.split(':', 1)[1]
                last_update = name
                url = None
                if 'imageinfo' in body:
                    url = body['imageinfo'][0]['url']
                else:
                    url = image_object['Digimon noimage.jpg'] if 'Digimon noimage.jpg' in image_object else NO_IMG_URL
                if name not in image_object or image_object[name] != url:
                    image_object[name] = url
                    changed = True
                    print(f'New URL found for image_id: {name}: {url}')
                # count += 1
                # print(f'{count}/{len(image_list)}')
    except Exception:
        print("Exception in user code:")
        print("-"*60)
        traceback.print_exc(file=sys.stdout)
        print("-"*60)
        print(last_update)
    finally:
        if changed:
            with open('image_urls.json', 'w') as outfile:
                json.dump(image_object, outfile, sort_keys=True)

def test_digimon_with_no_vpet_sprites():
    digi_obj = {}
    try:
        with open('digi_list.json') as infile:
            digi_obj = json.load(infile)
    except Exception:
        print("Exception in user code:")
        print("-"*60)
        traceback.print_exc(file=sys.stdout)
        print("-"*60)
    count = 0
    for digimon in digi_obj.keys():
        images = get_images_of_digimon(digimon, digi_obj)
        vpet_img = next((i for i in images if (i.endswith('.gif') or i.endswith('.png') and 'vpet' in i) or (i.endswith('.png') and 'dot' in i)), None)
        if not vpet_img:
            print(digimon)
            count += 1
    print(count)

test_digimon_with_no_vpet_sprites()