#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1] / 'resources' / 'geojson'
zero = sorted([p for p in root.rglob('*.geojson') if p.is_file() and p.stat().st_size == 0])
if zero:
    print('Zero-byte GeoJSON files detected:')
    for p in zero:
        print('-', p)
    sys.exit(1)
print('No zero-byte GeoJSON files detected.')
