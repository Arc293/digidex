from bs4 import BeautifulSoup

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
    print(soup.text)

replace_ref_tag_with_template("<div> [[Beelzebumon (X-Antibody)]] (with [[Barbamon]], [[Belphemon: Rage Mode]], [[Demon]], [[Leviamon]], [[Lilithmon]], or [[Lucemon: Falldown Mode]]<ref name=DM02-104/>)</div>")