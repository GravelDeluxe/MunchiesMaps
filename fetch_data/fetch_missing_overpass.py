#!/usr/bin/env python3
"""Fetch missing/problematic GeoJSON files by wrapping check_missing_json + fetch_overpass."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(ROOT_DIR / "fetch_data") not in sys.path:
    sys.path.insert(0, str(ROOT_DIR / "fetch_data"))

from scripts.check_missing_json import build_expected_geojson_paths, collect_file_statuses  # noqa: E402
from fetch_overpass import load_config, run  # noqa: E402

PROBLEM_STATUSES = ["missing_file", "empty_file", "invalid_json", "invalid_feature_collection"]


def parse_problems(
    expected_paths: list[tuple[str, str, str, Path]],
    status_report: dict[str, Any],
    countries_filter: set[str] | None = None,
) -> tuple[set[str], set[str], list[str]]:
    path_to_combo = {
        str(path.relative_to(ROOT_DIR)): (country, region_id, category)
        for country, region_id, category, path in expected_paths
    }

    region_ids: set[str] = set()
    categories: set[str] = set()
    combos: list[str] = []

    for country, statuses in status_report.get("problem_by_country", {}).items():
        if countries_filter and country not in countries_filter:
            continue
        for status in PROBLEM_STATUSES:
            for problem in statuses.get(status, []):
                key = problem.get("path", "")
                combo = path_to_combo.get(key)
                if not combo:
                    continue
                _, region_id, category = combo
                region_ids.add(region_id)
                categories.add(category)
                combos.append(f"{problem['path']} ({status})")

    return region_ids, categories, sorted(set(combos))


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch only missing/problematic GeoJSON files based on config expectations.")
    parser.add_argument("--dry-run", action="store_true", help="Only show what would be fetched.")
    parser.add_argument("--countries", type=str, default="", help="Comma-separated country ids to limit fetching.")
    parser.add_argument(
        "--include-empty-feature-collections",
        action="store_true",
        help="Also include valid empty FeatureCollections as refetch targets.",
    )
    args = parser.parse_args()

    config = load_config()
    expected_paths, config_errors = build_expected_geojson_paths(config)
    if config_errors:
        for error in config_errors:
            print(f"[problem-fetch][config] {error}")

    status_report = collect_file_statuses(
        expected_paths,
        include_empty_feature_collections=args.include_empty_feature_collections,
    )

    countries_filter = {c.strip().lower() for c in args.countries.split(",") if c.strip()}
    region_ids, categories, combos = parse_problems(
        expected_paths,
        {"problem_by_country": status_report.get("problem_by_country", {})},
        countries_filter=countries_filter or None,
    )

    if not combos:
        print("No missing/problematic files. Nothing to fetch.")
        return 0

    print(f"[problem-fetch] regions={len(region_ids)} | categories={len(categories)} | files={len(combos)}")
    for combo in combos:
        print(f"- {combo}")

    if args.dry_run:
        print("[problem-fetch] dry-run enabled; no fetch executed.")
        return 0

    run(region_filter=region_ids, layer_filter=categories, country_filter=None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
