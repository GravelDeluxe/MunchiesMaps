#!/usr/bin/env python3
import json
from pathlib import Path
from fetch_overpass import load_config, normalize_regions

config=load_config()
regions=normalize_regions(config)
ids=set(); paths=set()
for r in regions:
    if r['id'] in ids: raise SystemExit(f"duplicate id: {r['id']}")
    ids.add(r['id'])
    if r['path'] in paths: raise SystemExit(f"duplicate path: {r['path']}")
    paths.add(r['path'])
for c in ['germany','czechia','austria','switzerland']:
    if c not in (config.get('countries') or {}): raise SystemExit(f'missing country in countries: {c}')
legacy=config.get('regions') or []
for r in legacy:
    if r.get('country') in {'germany','czechia','austria','switzerland'}:
        raise SystemExit(f'legacy region still present: {r.get("country")} {r.get("id")}')
manifest=json.loads(Path('resources/geojson/manifest.json').read_text())
for r in manifest.get('regions',[]):
    if r.get('country')=='germany':
        p=r.get('path','')
        if not p.startswith('germany/de-'):
            raise SystemExit(f'legacy germany path in manifest: {p}')
print('validation_ok')
