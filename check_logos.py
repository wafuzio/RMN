#!/usr/bin/env python3
import json
from pathlib import Path

brands = json.load(open('config/brands.json'))
logo_db = json.load(open('output/brand_logos/brand_logo_database.json'))
logos_dir = Path('output/brand_logos')

examples = ['Always', 'Banquet', 'Bar-S', 'Baked', 'Babybel']

def slug(name):
    import re
    return re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')

print('Checking brands that logo_scout says are missing:\n')

for name in examples:
    s = slug(name)
    data = logo_db['brands'].get(s)
    
    if data:
        logo_file = data.get('logo_file', '')
        path = logos_dir / logo_file if logo_file else None
        exists = path.exists() if path else False
        
        print(f'{name} (slug: {s}):')
        print(f'  In database: Yes')
        print(f'  Logo file: {logo_file}')
        print(f'  File exists: {exists}')
        if exists:
            print(f'  Full path: {path}')
    else:
        print(f'{name} (slug: {s}):')
        print(f'  In database: No')
    print()
