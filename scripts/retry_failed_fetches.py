#!/usr/bin/env python3
"""Retry failed matrix fetch tasks from JSONL failure artifacts."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_tasks(failures_dir: Path) -> list[dict[str, str]]:
    tasks: dict[tuple[str, str, str], dict[str, str]] = {}
    for file in sorted(failures_dir.glob("*.jsonl")):
        try:
            for line in file.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                country = str(item.get("country", "")).strip().lower()
                region_key = str(item.get("region_key", "")).strip().lower()
                category = str(item.get("category", "")).strip().lower()
                if not (country and region_key and category):
                    continue
                tasks[(country, region_key, category)] = {
                    "country": country,
                    "region_key": region_key,
                    "category": category,
                }
        except OSError:
            continue
    return list(tasks.values())


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--failures-dir", required=True)
    p.add_argument("--max-workers", type=int, default=1)
    p.add_argument("--pause-seconds", type=float, default=7.0)
    args = p.parse_args()

    if args.max_workers != 1:
        print("[warn] max_workers>1 currently not implemented; running sequentially.")

    failures_dir = Path(args.failures_dir)
    tasks = load_tasks(failures_dir)
    if not tasks:
        print("No failed fetch tasks to retry")
        return 0

    after_retry = ROOT / "artifacts" / "fetch-failures-after-retry.jsonl"
    after_retry.parent.mkdir(parents=True, exist_ok=True)
    after_retry.write_text("", encoding="utf-8")

    for idx, task in enumerate(tasks, start=1):
        print(f"[retry] ({idx}/{len(tasks)}) {task['country']}/{task['region_key']}:{task['category']}")
        cmd = [
            sys.executable,
            "fetch_data/fetch_overpass.py",
            "--countries",
            task["country"],
            "--regions",
            task["region_key"],
            "--layers",
            task["category"],
            "--failure-log-jsonl",
            str(after_retry),
        ]
        proc = subprocess.run(cmd, cwd=ROOT)
        if proc.returncode == 0:
            print("[retry] success")
        else:
            print("[retry] failed")
        time.sleep(max(0.0, args.pause_seconds))

    remaining = [line for line in after_retry.read_text(encoding="utf-8").splitlines() if line.strip()]
    if remaining:
        print(f"[retry] remaining failures: {len(remaining)}")
        return 1
    print("[retry] all retry tasks successful")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
