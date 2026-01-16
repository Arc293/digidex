import json
import re

def extract_image_links(wikitext, pagename):
    """
    Extracts image filenames from wikitext, handling [[File:]] and [[Image:]]
    formats and replacing {{PAGENAME}} placeholders.

    Args:
        wikitext (str): The wikitext content.
        pagename (str): The value to replace {{PAGENAME}} with.

    Returns:
        list: A list of extracted image filenames.
    """
    # Regex to find [[File:...]] or [[Image:...]] tags
    # It captures the content inside the tag until a | or ]] is found
    pattern = re.compile(r'\[\[(?:File|Image):([^|\]]+)')
    
    matches = pattern.findall(wikitext)
    
    image_links = []
    for match in matches:
        # Replace the placeholder with the actual page name
        cleaned_link = match.replace('{{PAGENAME}}', pagename)
        # A more complex placeholder replacement for other variables
        cleaned_link = re.sub(r'\{\{\{.*?\|(.*?)\}\}\}', r'\1', cleaned_link)
        image_links.append(cleaned_link.strip())
        
    return image_links

def main():
    """
    Main function to demonstrate the image link extraction.
    """
    try:
        with open('template_html_data.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print("Error: 'template_html_data.json' not found.")
        return

    # Demonstrate with all templates in the file
    for template_name, wikitext in data.items():
        # Let's assume a sample pagename for demonstration
        sample_pagename = f"{template_name}_Card"
        
        print(f"--- Parsing images for template '{template_name}' with PAGENAME '{sample_pagename}' ---")
        image_links = extract_image_links(wikitext, sample_pagename)
        
        if image_links:
            print("Found image links:")
            for link in image_links:
                print(f"- {link}")
        else:
            print("No image links found.")
        print("\n")

if __name__ == '__main__':
    main()
