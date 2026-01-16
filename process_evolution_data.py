import json
import os
import re
from typing import Any, Dict, List, Set

def get_all_digimon_names(json_dir: str) -> Set[str]:
    """
    Scans all JSON files in a directory to compile a set of all Digimon names.

    Args:
        json_dir: The directory containing the JSON files.

    Returns:
        A set of all unique Digimon names.
    """
    digimon_names = set()
    for filename in os.listdir(json_dir):
        if filename.endswith(".json"):
            with open(os.path.join(json_dir, filename), 'r') as f:
                data = json.load(f)
                digimon_names.update(data.keys())
    return digimon_names

def parse_wikitext(wikitext: str, digimon_names: Set[str]) -> Dict[str, Any]:
    """
    Parses a wikitext string to extract evolution data.

    Args:
        wikitext: The wikitext string to parse.
        digimon_names: A set of all valid Digimon names for validation.

    Returns:
        A dictionary containing the parsed evolution data.
    """
    # Default values
    result = {
        "is_special_evo": False,
        "special_evo_type": "",
        "unknown_param": [],
        "references": [],
        "type": "unknown",
        "has_fusees": False,
        "name": "",
        "name_text": "",
        "link": "",
        "fusees": []
    }

    # Extract references
    references = re.findall(r'{{r[a-z]+\|([^}]+)}}', wikitext)
    if references:
        result["references"] = [ref.strip() for ref in references]
        wikitext = re.sub(r'{{r[a-z]+\|[^}]+}}', '', wikitext).strip()

    # Fusion check
    fusion_keywords = [" with or without ", " with "]
    for keyword in fusion_keywords:
        if keyword in wikitext:
            parts = wikitext.split(keyword)
            # The first part is the main digimon, the rest are fusees
            wikitext = parts[0]
            result["has_fusees"] = True
            # Parse the fusees recursively
            for part in parts[1:]:
                # This is a simplified approach; a full recursive parse might be needed for complex cases
                fusee_match = re.findall(r"'''\[\[([^\]]+)\]]'''", part)
                for fusee in fusee_match:
                    if fusee in digimon_names:
                        result["fusees"].append({"type": "digimon", "name": fusee})
                    else:
                         result["fusees"].append({"type": "non_digimon", "name": fusee})
            break # Stop after finding the first fusion keyword

    # Type: digimon
    match = re.search(r"'''\[\[([^\]]+)\]]'''", wikitext)
    if match:
        name = match.group(1).strip()
        if name in digimon_names:
            result["type"] = "digimon"
            result["name"] = name
            return result

    # Type: card
    match = re.search(r"\[\[([^|]+)\|([^\]]+)\]]", wikitext)
    if match:
        name_text = match.group(2).strip()
        if "from the ''Digimon Card Game''" in name_text:
            result["type"] = "card"
            result["name_text"] = name_text
            result["link"] = match.group(1).strip()
            return result

    # Type: egg
    if "[[Digitama]]" in wikitext:
        result["type"] = "egg"
        result["name_text"] = "Digitama"
        return result

    # Type: any
    if wikitext.lower().startswith("any "):
        result["type"] = "any"
        # Clean up the wikitext to get a readable name
        name_text = re.sub(r'\[\[:?([^|\]]+)\]\]', r'\1', wikitext)
        name_text = re.sub(r'\[\[[^|]+\|([^\]]+)\]\]', r'\1', name_text)
        result["name_text"] = name_text.strip()
        return result

    # Type: non_digimon (heuristic: contains "from" but not a recognized pattern)
    # This is a simple heuristic and might need refinement.
    if " from " in wikitext and not result["name"]:
         result["type"] = "non_digimon"
         result["name"] = wikitext.strip()
         return result


    # Fallback for names that are just links
    match = re.search(r"\[\[([^\]]+)\]]", wikitext)
    if match:
        name = match.group(1).strip()
        if name in digimon_names:
            result["type"] = "digimon"
            result["name"] = name
            return result
        else:
            result["type"] = "non_digimon"
            result["name"] = name
            return result


    return result

def process_all_files(json_dir: str, digimon_names: Set[str]) -> Dict[str, Any]:
    """
    Processes all JSON files in a directory to parse evolution data.

    Args:
        json_dir: The directory containing the JSON files.
        digimon_names: A set of all valid Digimon names for validation.

    Returns:
        A dictionary containing the parsed evolution data for all Digimon.
    """
    all_parsed_data = {}
    for filename in os.listdir(json_dir):
        if filename.endswith(".json"):
            with open(os.path.join(json_dir, filename), 'r') as f:
                data = json.load(f)
                for digimon_name, digimon_data in data.items():
                    if digimon_name not in all_parsed_data:
                        all_parsed_data[digimon_name] = {}

                    for evo_key in ["evolve_from", "evolve_to"]:
                        if evo_key in digimon_data:
                            parsed_list = []
                            for wikitext in digimon_data[evo_key]:
                                parsed_list.append(parse_wikitext(wikitext, digimon_names))
                            all_parsed_data[digimon_name][evo_key] = parsed_list
    return all_parsed_data


if __name__ == "__main__":
    json_directory = "evo_json_splits/"
    output_file = "parsed_evolutions.json"

    print("Step 1: Aggregating all Digimon names...")
    digimon_names = get_all_digimon_names(json_directory)
    # Manually add names for testing fusion that might not be in the keys
    digimon_names.add("Aquilamon")
    digimon_names.add("Gatomon")
    digimon_names.add("Silphymon")
    print(f"Found {len(digimon_names)} unique Digimon names.")

    # --- Test Cases ---
    print("\n--- Parser Test ---")
    test_cases = {
        "digimon": "'''[[Agumon]]'''{{rfe|DA:|01|''Tokyo: Digital Crisis''|b}}",
        "card": "[[Digimon Card Game Colors and Levels#Black Lv.5 Digimon|Any Black Lv.5 Digimon from the ''Digimon Card Game'']]{{rfc|EX9|055 (DCG)}}",
        "egg": "'''[[Digitama]]'''{{rfe|DA:|01|''Tokyo: Digital Crisis''|b}}",
        "any": "Any [[Child]] [[:Category:Dragon's Roar|Dragon's Roar]] Digimon from [[Card Game Alpha]]{{rfc|Da|557}}",
        "non_digimon": "[[Victory Uchida]]",
        "fusion": "'''[[Silphymon]]''' with '''[[Aquilamon]]''' and '''[[Gatomon]]'''"
    }

    for evo_type, wikitext in test_cases.items():
        parsed_data = parse_wikitext(wikitext, digimon_names)
        print(f"Input ({evo_type}): {wikitext}")
        print(f"Output: {json.dumps(parsed_data, indent=2)}\n")


    print("\nStep 2: Processing all evolution data...")
    parsed_data = process_all_files(json_directory, digimon_names)
    print(f"Processed evolution data for {len(parsed_data)} Digimon.")

    print(f"\nStep 3: Saving structured data to '{output_file}'...")
    with open(output_file, 'w') as f:
        json.dump(parsed_data, f, indent=2)
    print("Done.")
