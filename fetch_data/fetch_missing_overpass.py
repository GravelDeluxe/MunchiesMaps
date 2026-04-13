#!/usr/bin/env python3
"""Fetch only missing GeoJSON files by wrapping check_missing_json + fetch_overpass."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.check_missing_json import (  # noqa: E402
    build_expected_geojson_paths,
    collect_missing_paths,
    load_config,
)
from fetch_overpass import normalize_regions, run  # noqa: E402

CONFIG_PATH = ROOT_DIR / "fetch_data" / "config.yml"
RESOURCE_ROOT = ROOT_DIR / "resources" / "geojson"


def parse_missing(config: dict[str, Any], missing_by_country: dict[str, list[Path]]) -> tuple[set[str], set[str], list[str]]:
    """Resolve missing files into fetch_overpass filters."""
    regions = normalize_regions(config)
    region_by_path = {
        str(region.get("path", "")).strip().lower().strip("/"): region
        for region in regions
        if str(region.get("path", "")).strip()
    }

    region_ids: set[str] = set()
    categories: set[str] = set()
    combos: list[str] = []

    for paths in missing_by_country.values():
        for missing_path in paths:
            try:
                relative = missing_path.resolve().relative_to(RESOURCE_ROOT.resolve())
            except ValueError:
                continue

            region_path = relative.parent.as_posix().lower().strip("/")
            category = relative.stem

            region = region_by_path.get(region_path)
            if not region:
                continue

            region_id = str(region.get("id", "")).strip()
            if not region_id or not category:
                continue

            region_ids.add(region_id)
            categories.add(category)
            combos.append(f"{region_path}:{category}")

    return region_ids, categories, sorted(set(combos))


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch only missing GeoJSON files based on config expectations.")
    parser.add_argument("--dry-run", action="store_true", help="Only show what would be fetched.")
    args = parser.parse_args()

    config = load_config(CONFIG_PATH)
    expected_paths, config_errors = build_expected_geojson_paths(config)
    if config_errors:
        for error in config_errors:
            print(f"[missing-fetch][config] {error}")

    missing_by_country = collect_missing_paths(expected_paths)
    missing_count = sum(len(paths) for paths in missing_by_country.values())

    if missing_count == 0:
        print("No missing files. Nothing to fetch.")
        return 0

    region_ids, categories, combos = parse_missing(config, missing_by_country)

    print(f"[missing-fetch] regions={len(region_ids)} | categories={len(categories)} | files={missing_count}")
    if combos:
        print("[missing-fetch] missing combinations:")
        for combo in combos:
            print(f"- {combo}")

    if args.dry_run:
        print("[missing-fetch] dry-run enabled; no fetch executed.")
        return 0

    run(region_filter=region_ids, category_filter=categories, country_filter=None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
