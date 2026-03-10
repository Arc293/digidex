import requests
import json
import sys, traceback
from clint.textui import progress
import wikitextparser as wtp
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
from tqdm import tqdm
from PIL import Image
from io import BytesIO

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