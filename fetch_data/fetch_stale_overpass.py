#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument('--config', required=True)
    p.add_argument('--targets', required=True)
    p.add_argument('--retry-attempts', type=int, default=3)
    p.add_argument('--retry-sleep', type=int, default=60)
    p.add_argument('--output-dir', required=True)
    p.add_argument('--failed-output', required=True)
    p.add_argument('--debug', action='store_true')
    return p.parse_args()


def load_targets(path: Path) -> list[dict]:
    if not path.exists():
        raise SystemExit(f'targets file not found: {path}')
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, list):
        raise SystemExit('targets file must contain a JSON list')
    return data


def run_target_via_legacy_cli(target: dict, output_dir: Path, debug: bool) -> tuple[bool, str]:
    country = str(target.get('country', '')).strip()
    region = str(target.get('region', '')).strip()
    category = str(target.get('category', '')).strip()
    rel_path = Path(str(target.get('path', '')).strip())

    if not country or not region or not category:
        return False, 'missing_target_fields(country/region/category)'
    if not rel_path.parts:
        return False, 'missing_target_path'

    cmd = [
        sys.executable,
        'fetch_data/fetch_overpass.py',
        '--countries', country,
        '--regions', region,
        '--layers', category,
    ]

    if debug:
        print(f"[debug] target country={country} region={region} category={category}")
        print(f"[debug] output_path={output_dir / rel_path}")
        print('[debug] fetch_impl=legacy_cli fetch_data/fetch_overpass.py')
        print(f"[debug] command={' '.join(cmd)}")

    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if proc.stdout:
        print(proc.stdout, end='')
    if proc.stderr:
        print(proc.stderr, end='', file=sys.stderr)

    if debug:
        endpoint_lines = [
            line for line in proc.stdout.splitlines()
            if '[run] Endpoints:' in line or line.startswith('[req]') or line.startswith('[smoke]')
        ]
        for line in endpoint_lines:
            print(f'[debug] {line}')
        if proc.returncode != 0:
            print(f'[debug] exception_class=SubprocessError exception_message=legacy_fetch_exit_{proc.returncode}')

    src = ROOT / rel_path
    dst = output_dir / rel_path
    if proc.returncode == 0 and src.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        return True, ''
    if proc.returncode == 0 and not src.exists():
        return False, 'legacy_fetch_missing_expected_output'

    err = f'legacy_fetch_exit_code={proc.returncode}'
    for line in reversed(proc.stdout.splitlines()):
        if 'All Overpass endpoints failed.' in line or '[fail]' in line or '[error]' in line:
            err = line.strip()
            break
    return False, err


def main() -> None:
    args = parse_args()
    targets = load_targets(Path(args.targets))
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    failed: list[dict] = []
    successful = 0

    for target in targets:
        ok = False
        last_error = 'unknown'
        for attempt in range(1, args.retry_attempts + 1):
            ok, last_error = run_target_via_legacy_cli(target, out_dir, args.debug)
            if ok:
                successful += 1
                print(
                    f"[target] success country={target.get('country')} region={target.get('region')} "
                    f"category={target.get('category')} attempt={attempt}"
                )
                break
            print(
                f"[target] failure country={target.get('country')} region={target.get('region')} "
                f"category={target.get('category')} attempt={attempt} error={last_error}"
            )
            if attempt < args.retry_attempts:
                time.sleep(args.retry_sleep * attempt)

        if not ok:
            row = dict(target)
            row['error'] = last_error
            failed.append(row)

    failed_path = Path(args.failed_output)
    failed_path.parent.mkdir(parents=True, exist_ok=True)
    failed_path.write_text(json.dumps(failed, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f"summary total={len(targets)} successful={successful} failed={len(failed)} skipped=0 failed_output={failed_path}")


if __name__ == '__main__':
    main()
