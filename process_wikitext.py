import json
import os
import re
from collections import defaultdict

def parse_wikitext(wikitext):
    """Parses wikitext and returns a dictionary of parameters."""
    params = {}
    # This pattern finds all key-value pairs, like |key=value, until the next | or }}
    pattern = re.compile(r'\|\s*([^=]+?)\s*=\s*(.*?)\s*(?=\||\}\})', re.DOTALL)
    matches = pattern.findall(wikitext)
    for key, value in matches:
        params[key.strip()] = value.strip()
    return params

def structure_data(flat_data, mapping):
    """
    Transforms a flat dictionary of wikitext params into a structured, nested dictionary
    based on the provided mapping file.
    """
    structured_data = defaultdict(dict)
    # Temporary storage for array objects before they are finalized
    array_objects = defaultdict(dict)

    for key, value in flat_data.items():
        if key in mapping:
            map_info = mapping[key]
            group = map_info['group']
            field = map_info['field']

            if group in ['general', 'card_info']:
                if group not in structured_data:
                    structured_data[group] = {}
                if not map_info.get('array'):
                    # It's a simple key-value pair
                    
                    structured_data[group][field] = value
                else:
                    # This key is part of an array of objects
                    # obj_id = map_info.get('id', field) # Use field as id if no specific id is present
                    
                    # Find or create the object for this id within the group
                    if field not in structured_data[group]:
                        structured_data[group][field] = []
                    
                    # Add the field and value to the object
                    structured_data[group][field].append(value)
            else:
                if not map_info.get('array'):
                # It's a simple key-value pair
                    if group not in structured_data:
                        structured_data[group] = {}
                    structured_data[group][field] = value
                else:
                    # This key is part of an array of objects
                    obj_id = map_info.get('id', field) # Use field as id if no specific id is present
                    
                    # Find or create the object for this id within the group
                    if obj_id not in array_objects[group]:
                        array_objects[group][obj_id] = {}
                    
                    # Add the field and value to the object
                    array_objects[group][obj_id][field] = value

    # Convert the temporary array_objects into final lists in structured_data
    for group, objects in array_objects.items():
        structured_data[group] = list(objects.values())

    # Convert the temporary array_objects into final lists in structured_data
    # for group, objects in array_objects.items():
    #     structured_data[group] = list(objects.values())

    # Clean up any empty groups that might have been created
    return {k: v for k, v in structured_data.items() if v}

def main():
    """
    Main function to read wikitext files, parse them, structure the data,
    and save the output as structured JSON files.
    """
    # Load the parameter mapping
    try:
        with open('final_param_mapping.json', 'r') as f:
            mapping = json.load(f)
    except FileNotFoundError:
        print("Error: 'final_param_mapping.json' not found. Please ensure the mapping file exists.")
        return

    # input_dir = 'tcg_wikitexts/'
    # output_dir = 'tcg_json/'

    # if not os.path.exists(output_dir):
    #     os.makedirs(output_dir)

    # if not os.path.exists(input_dir):
    #     print(f"Error: Input directory '{input_dir}' not found.")
    #     return
        
    # processed_files = 0
    # for filename in os.listdir(input_dir):
    #     if filename.endswith('.txt'):
    #         filepath = os.path.join(input_dir, filename)
    #         with open(filepath, 'r', encoding='utf-8') as f:
    #             content = f.read()

            # 1. Parse the wikitext to get a flat dictionary
            # flat_data = parse_wikitext(content)

            # 2. Structure the flat data using the mapping
            # structured_data = structure_data(flat_data, mapping)
    with open('tcg_scrap.json', 'r') as infile:
        tcg_info = json.load(infile)

        output = {}

        for game, game_data in tcg_info.items():
            output[game] = {}
            for card, card_data in game_data.items():
                output[game][card] = structure_data(card_data, mapping)
        
        with open('tcg_parsed.json', 'w') as outfile:
            json.dump(output, outfile)


if __name__ == '__main__':
    main()
