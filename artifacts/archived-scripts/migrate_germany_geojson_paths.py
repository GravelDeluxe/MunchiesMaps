#!/usr/bin/env python3
import argparse, json, shutil
from pathlib import Path

GERMANY_REGION_PATH_MAPPING = {
    "baden-wuerttemberg": "de-bw", "bayern": "de-by", "berlin": "de-be", "brandenburg": "de-bb",
    "bremen": "de-hb", "hamburg": "de-hh", "hessen": "de-he", "mecklenburg-vorpommern": "de-mv",
    "niedersachsen": "de-ni", "nordrhein-westfalen": "de-nw", "rheinland-pfalz": "de-rp", "saarland": "de-sl",
    "sachsen": "de-sn", "sachsen-anhalt": "de-st", "schleswig-holstein": "de-sh", "thueringen": "de-th",
}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--overwrite', action='store_true')
    ap.add_argument('--delete-old', action='store_true')
    args=ap.parse_args()
    if args.delete_old and args.dry_run:
        raise SystemExit('--delete-old cannot be used with --dry-run')
    root=Path('resources/geojson/germany')
    summary={'copied':0,'skipped_existing':0,'missing_source_dir':0,'deleted_old_dir':0,'files':[]}
    for old,new in GERMANY_REGION_PATH_MAPPING.items():
        src=root/old; dst=root/new
        if not src.exists():
            print(f'missing_source_dir {src}')
            summary['missing_source_dir']+=1
            summary['files'].append({'status':'missing_source_dir','source_dir':str(src),'target_dir':str(dst)})
            continue
        dst.mkdir(parents=True,exist_ok=True)
        for f in src.glob('*.geojson'):
            t=dst/f.name
            if t.exists() and not args.overwrite:
                print(f'skipped_existing {t}')
                summary['skipped_existing']+=1
                summary['files'].append({'status':'skipped_existing','source':str(f),'target':str(t)})
                continue
            if not args.dry_run:
                shutil.copy2(f,t)
            print(f'copied {f} -> {t}')
            summary['copied']+=1
            summary['files'].append({'status':'copied','source':str(f),'target':str(t)})
        if args.delete_old:
            shutil.rmtree(src)
            print(f'deleted_old_dir {src}')
            summary['deleted_old_dir']+=1
            summary['files'].append({'status':'deleted_old_dir','source_dir':str(src)})
    Path('artifacts').mkdir(exist_ok=True)
    out=Path('artifacts/germany_geojson_path_migration_summary.json')
    out.write_text(json.dumps(summary,indent=2,ensure_ascii=False)+"\n")
    print(json.dumps({k:summary[k] for k in ['copied','skipped_existing','missing_source_dir','deleted_old_dir']}))

if __name__=='__main__':
    main()
