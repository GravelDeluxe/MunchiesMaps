#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
import yaml
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "fetch_data") not in sys.path:
    sys.path.insert(0, str(ROOT / "fetch_data"))
from fetch_data import fetch_overpass

def parse_args():
    p=argparse.ArgumentParser()
    p.add_argument('--config', required=True)
    p.add_argument('--days', required=True, type=int)
    p.add_argument('--country')
    p.add_argument('--category')
    p.add_argument('--output', required=True)
    p.add_argument('--include-empty', dest='include_empty', action='store_true', default=True)
    p.add_argument('--exclude-empty', dest='include_empty', action='store_false')
    return p.parse_args()

def validate_days(days:int):
    if days == 0 or days < -1:
        raise SystemExit('--days must be -1 or a positive integer')

def get_commit_date(path: Path) -> datetime|None:
    rel = path.relative_to(ROOT)
    proc = subprocess.run(['git','log','-1','--format=%cI','--',str(rel)], cwd=ROOT, capture_output=True, text=True)
    if proc.returncode != 0:
        return None
    txt=proc.stdout.strip()
    if not txt:
        return None
    try: return datetime.fromisoformat(txt.replace('Z','+00:00'))
    except ValueError: return None

def geojson_issue(path:Path, include_empty:bool)->str|None:
    if not path.exists(): return 'missing_file'
    if path.stat().st_size == 0: return 'empty_file'
    try: data=json.loads(path.read_text(encoding='utf-8'))
    except Exception: return 'invalid_json'
    if not isinstance(data,dict) or data.get('type')!='FeatureCollection': return 'invalid_geojson'
    if 'features' not in data: return 'missing_features'
    if not isinstance(data.get('features'), list): return 'invalid_geojson'
    if include_empty and len(data['features'])==0: return 'empty_features'
    return None

def main():
    a=parse_args(); validate_days(a.days)
    cfg=yaml.safe_load(Path(a.config).read_text(encoding='utf-8')) or {}
    regions=fetch_overpass.normalize_regions(cfg)
    categories=cfg.get('categories',{})
    if not isinstance(categories, dict): raise SystemExit('categories must be object')
    now=datetime.now(timezone.utc)
    targets=[]; seen=set()
    for region in regions:
        country=str(region.get('country','')).strip().lower()
        if a.country and country!=a.country.strip().lower(): continue
        region_id=str(region.get('region') or region.get('id'))
        for category in categories.keys():
            if a.category and category!=a.category: continue
            rel_path=Path('resources/geojson') / str(region['path']) / f'{category}.geojson'
            abs_path=ROOT/rel_path
            reason=geojson_issue(abs_path, a.include_empty)
            commit_dt=None; age_days=None
            if reason is None:
                if a.days == -1:
                    reason='full_refresh'
                else:
                    commit_dt=get_commit_date(abs_path)
                    if commit_dt is None:
                        reason='no_git_commit_date'
                    else:
                        age_days=(now-commit_dt.astimezone(timezone.utc)).days
                        if age_days > a.days:
                            reason='older_than_threshold'
            if reason:
                key=(country,region_id,category,str(rel_path))
                if key in seen: continue
                seen.add(key)
                item={'country':country,'region':region_id,'category':category,'path':str(rel_path),'reason':reason}
                if commit_dt is not None: item['last_commit_date']=commit_dt.isoformat()
                if age_days is not None: item['age_days']=age_days
                targets.append(item)
    out=Path(a.output); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(targets,indent=2,ensure_ascii=False), encoding='utf-8')
    print(f'wrote {len(targets)} targets to {out}')

if __name__=='__main__': main()
