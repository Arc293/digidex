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

def get_image_list(digi_obj:dict)->list:
    image_set = set()
    for digi_data in digi_obj.values():
        if 'images' in digi_data:
            image_set.update([f"Image:{image.split('!')[0]}" for image in digi_data['images']])
        if 'image_gallery' in digi_data:
            image_set.update([f"Image:{image['image']}" for image in digi_data['image_gallery']])
    return list(image_set)


def scrap_image_urls():
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
        image_list = get_image_list(digi_obj)
        print(len(image_list))
        count = 0
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
                    print(f'{name} did not have an image url')
                    continue
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

def download_file(file_path, url):
    try:
        response = requests.get(url)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error downloading {file_path}: {e}")
        return None

    if response.status_code == 200:
        # Extract the directory and filename from the file path
        directory, filename = os.path.split(file_path)
        # Create the directory if it doesn't exist
        os.makedirs(directory, exist_ok=True)
        # Save the file as JPEG
        try:
            image = Image.open(BytesIO(response.content))
            image.save(file_path.replace('\u200e', '').strip())
            return file_path
        except IOError:
            return None
    else:
        return None

def download_images():
    image_object = {}
    digi_obj = {}
    try:
        with open('image_urls.json', encoding='utf-8') as infile:
            image_object = json.load(infile)
    except Exception:
        print("Exception in user code:")
        print("-"*60)
        traceback.print_exc(file=sys.stdout)
        print("-"*60)

    try:
        with open('digi_list.json', encoding='utf-8') as infile:
            digi_obj = json.load(infile)
    except Exception:
        print("Exception in user code:")
        print("-"*60)
        traceback.print_exc(file=sys.stdout)
        print("-"*60)
    dl_list = []
    img_path  = './digimon_images'
    for name, data in digi_obj.items():
        image_list = get_image_list({'x': data})
        for image in image_list:
            image = image.split(':', 1)[1]
            if image not in image_object:
                print(f'{image} was not found')
                continue
            path = f'{img_path}/{name}/{image}'
            if os.path.isfile(path):
                continue
            dl_list.append({'filepath': path, 'url': image_object[image]})
    # Create a ThreadPoolExecutor with maximum 256 worker threads
    executor = ThreadPoolExecutor(max_workers=256)

    # Use a list to store the download tasks
    tasks = []

    # Use tqdm to create a progress bar
    with tqdm(total=len(dl_list)) as progress_bar:
        error_count = 0
        # Submit the download tasks
        for file in dl_list:
            task = executor.submit(download_file, file['filepath'], file['url'])
            tasks.append(task)

        # Process the completed tasks
        for completed_task in as_completed(tasks):
            result = completed_task.result()
            if result is None:
                error_count += 1
            progress_bar.update(1)

    print(f"All downloads completed, errors: {error_count}")

download_images()