#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, time, sys
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
FETCH_DIR = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(FETCH_DIR) not in sys.path:
    sys.path.insert(0, str(FETCH_DIR))
from fetch_data import fetch_overpass
import overpass_templates

TRANSIENT_CODES={429,500,502,503,504}

def is_valid_geojson(data):
    return isinstance(data,dict) and data.get('type')=='FeatureCollection' and isinstance(data.get('features'),list)

def run_target(config, categories, target, retry_attempts, retry_sleep, output_dir):
    region_map={(str(r.get('country')).lower(), str(r.get('region') or r.get('id'))):r for r in fetch_overpass.normalize_regions(config)}
    region=region_map.get((target['country'], target['region']))
    if not region: return False, 'region_not_found'
    cat=target['category']
    body=categories.get(cat)
    if not body: return False,'category_not_found'
    attempts=fetch_overpass.build_query_attempts(region)
    last_error='unknown'; endpoint=''
    for attempt in range(1, retry_attempts+1):
        for query_attempt in attempts:
            query=fetch_overpass.build_query(region, cat, body, config.get('timeout',300), query_attempt['mode'], query_attempt['match_type'])
            try:
                response=fetch_overpass.request_with_retry(config.get('endpoints',[]), query, config.get('timeout',300), {
                    'region':target['region'],'country':target['country'],'category':cat,'query_attempt':f"{query_attempt['mode']}/{query_attempt['match_type']}"
                })
                endpoint=response.get('_meta',{}).get('endpoint','')
                geo=fetch_overpass.convert_to_geojson(response.get('elements',[]), cat)
                if not is_valid_geojson(geo):
                    raise RuntimeError('invalid_geojson_result')
                dest=output_dir/target['path']
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(json.dumps(geo, ensure_ascii=False, indent=2), encoding='utf-8')
                print(f"[target] success country={target['country']} region={target['region']} category={cat} output={dest} attempt={attempt} endpoint={endpoint}")
                return True,''
            except Exception as exc:
                last_error=str(exc)
                print(f"[target] failure country={target['country']} region={target['region']} category={cat} attempt={attempt} endpoint={endpoint} error={last_error}")
        if attempt < retry_attempts:
            time.sleep(retry_sleep * attempt)
    return False,last_error

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--config', required=True)
    p.add_argument('--targets', required=True)
    p.add_argument('--retry-attempts', type=int, default=3)
    p.add_argument('--retry-sleep', type=int, default=60)
    p.add_argument('--output-dir', required=True)
    p.add_argument('--failed-output', required=True)
    a=p.parse_args()
    config=yaml.safe_load(Path(a.config).read_text(encoding='utf-8')) or {}
    categories_cfg=config.get('categories',{}) or {}
    config['categories']={k: fetch_overpass.get_category_function(v)() for k,v in categories_cfg.items()}
    targets=json.loads(Path(a.targets).read_text(encoding='utf-8')) if Path(a.targets).exists() else []
    out_dir=Path(a.output_dir); out_dir.mkdir(parents=True, exist_ok=True)
    failed=[]; succ=0
    for t in targets:
        ok,err=run_target(config, config['categories'], t, a.retry_attempts, a.retry_sleep, out_dir)
        if ok: succ+=1
        else:
            t2=dict(t); t2['error']=err; failed.append(t2)
    failed_path=Path(a.failed_output); failed_path.parent.mkdir(parents=True, exist_ok=True)
    failed_path.write_text(json.dumps(failed, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f"summary total={len(targets)} successful={succ} failed={len(failed)} skipped=0 failed_output={failed_path}")

if __name__=='__main__': main()
