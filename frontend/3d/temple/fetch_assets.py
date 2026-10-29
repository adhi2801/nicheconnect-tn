"""Download the CC0 materials and sky light the temple study uses, into ./tex.

They are not committed (each map is several megabytes). Every one is CC0 from
Poly Haven (https://polyhaven.com/license): free for any use, no credit required.

Run: python fetch_assets.py            (2K maps, enough for previews)
     python fetch_assets.py --4k       (adds 4K stone and paving for final renders)
"""
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
TEX = os.path.join(HERE, 'tex')
MATERIALS = ['large_sandstone_blocks', 'red_sandstone_pavement', 'palm_tree_bark', 'grass_path_2', 'granite_wall']
FINAL_4K = ['large_sandstone_blocks', 'red_sandstone_pavement']
MAPS = [('Diffuse', 'jpg'), ('nor_gl', 'jpg'), ('Rough', 'jpg'), ('Displacement', 'png'), ('AO', 'jpg')]
HDRI = 'kloofendal_38d_partly_cloudy_puresky'


def get_json(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'colyv-temple-study'})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def download(url, path):
    if os.path.exists(path):
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    req = urllib.request.Request(url, headers={'User-Agent': 'colyv-temple-study'})
    with urllib.request.urlopen(req, timeout=300) as r, open(path, 'wb') as f:
        f.write(r.read())
    print('saved', os.path.relpath(path, HERE))


def main():
    want_4k = '--4k' in sys.argv
    for name in MATERIALS:
        files = get_json(f'https://api.polyhaven.com/files/{name}')
        for res, sub in [('2k', '')] + ([('4k', '4k')] if want_4k and name in FINAL_4K else []):
            for kind, ext in MAPS:
                url = files.get(kind, {}).get(res, {}).get(ext, {}).get('url')
                if url:
                    download(url, os.path.join(TEX, name, sub, f'{kind}.{ext}'))
    hdr = get_json(f'https://api.polyhaven.com/files/{HDRI}')['hdri']['2k']['hdr']['url']
    download(hdr, os.path.join(TEX, 'hdri', 'sky_2k.hdr'))
    print('done; now render inscription.png (see README) before running vimana.py')


if __name__ == '__main__':
    main()
