#!/usr/bin/env python3
"""Validate configured country/region/category datasets in resources/geojson."""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR / "fetch_data") not in sys.path:
    sys.path.insert(0, str(ROOT_DIR / "fetch_data"))

from fetch_overpass import TAG_WHITELIST, classify_geojson_file, load_config, normalize_regions  # noqa: E402

RESOURCE_ROOT = ROOT_DIR / "resources" / "geojson"
PROBLEM_STATUSES = {
    "missing_file",
    "empty_file",
    "invalid_json",
    "invalid_feature_collection",
}


def normalize_categories(raw_categories: Any) -> list[str]:
    if isinstance(raw_categories, dict):
        return [str(key).strip() for key in raw_categories.keys() if str(key).strip()]
    if isinstance(raw_categories, list):
        return [str(item).strip() for item in raw_categories if str(item).strip()]
    return []


def get_country_categories(country_cfg: dict[str, Any], global_categories: list[str]) -> list[str]:
    country_categories = normalize_categories(country_cfg.get("categories"))
    return country_categories or global_categories


def build_expected_geojson_paths(config: dict[str, Any]) -> tuple[list[tuple[str, str, str, Path]], list[str]]:
    errors: list[str] = []
    countries_cfg = config.get("countries")
    if not isinstance(countries_cfg, dict) or not countries_cfg:
        return [], ["Config field 'countries' is missing or not a non-empty mapping."]

    global_categories = normalize_categories(config.get("categories"))
    if not global_categories:
        errors.append("Config field 'categories' is missing or empty; no expected files can be derived.")

    normalized_regions = normalize_regions(config)
    regions_by_country: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for region in normalized_regions:
        country = str(region.get("country", "")).strip().lower()
        if country:
            regions_by_country[country].append(region)

    config_set = set(global_categories)
    whitelist_set = set(TAG_WHITELIST.keys())
    if config_set != whitelist_set:
        only_config = sorted(config_set - whitelist_set)
        only_whitelist = sorted(whitelist_set - config_set)
        errors.append(
            "Category mismatch between config.yml and fetch_overpass TAG_WHITELIST: "
            f"only_in_config={only_config or '-'}; only_in_tag_whitelist={only_whitelist or '-'}"
        )
    if "accommodation" not in config_set:
        errors.append("Category 'accommodation' missing in config categories.")

    expected: list[tuple[str, str, str, Path]] = []
    for country_key, country_cfg in countries_cfg.items():
        if not isinstance(country_cfg, dict):
            errors.append(f"Country '{country_key}' has invalid definition (expected mapping).")
            continue
        country_id = str(country_key).strip().lower()
        categories = get_country_categories(country_cfg, global_categories)
        if not categories:
            errors.append(f"Country '{country_id}' has no categories after resolution.")
            continue
        if country_id not in regions_by_country:
            errors.append(f"Country '{country_id}' has no normalized regions.")
            continue
        for region in regions_by_country[country_id]:
            region_path = str(region.get("path", "")).strip().strip("/")
            if not region_path:
                errors.append(f"Region '{region.get('id')}' in country '{country_id}' has no valid path.")
                continue
            for category in categories:
                expected.append((country_id, str(region.get("id", "")), category, RESOURCE_ROOT / region_path / f"{category}.geojson"))

    return expected, errors


def collect_file_statuses(expected_paths: list[tuple[str, str, str, Path]], include_empty_feature_collections: bool = False) -> dict[str, Any]:
    by_country: dict[str, dict[str, list[dict[str, str]]]] = defaultdict(lambda: defaultdict(list))
    status_counts: dict[str, int] = defaultdict(int)

    for country, region_id, category, path in expected_paths:
        status = classify_geojson_file(path)
        status_counts[status] += 1
        if status in PROBLEM_STATUSES or (include_empty_feature_collections and status == "empty_feature_collection"):
            by_country[country][status].append(
                {
                    "region_id": region_id,
                    "category": category,
                    "path": str(path.relative_to(ROOT_DIR)),
                }
            )

    return {
        "problem_by_country": {country: dict(sorted(statuses.items())) for country, statuses in sorted(by_country.items())},
        "status_counts": dict(sorted(status_counts.items())),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-format", choices=["text", "json"], default="text")
    parser.add_argument(
        "--include-empty-feature-collections",
        action="store_true",
        help="Treat valid empty FeatureCollections as problematic for matrix/refetch purposes.",
    )
    args = parser.parse_args()

    expected_paths: list[tuple[str, str, str, Path]] = []
    config_errors: list[str] = []
    try:
        config = load_config()
        expected_paths, config_errors = build_expected_geojson_paths(config)
    except Exception as exc:  # noqa: BLE001
        config_errors.append(f"Configuration/load issue detected (report only): {exc}")

    status_data = collect_file_statuses(expected_paths, include_empty_feature_collections=args.include_empty_feature_collections)
    problem_by_country = status_data["problem_by_country"]

    summary = {
        "countries_checked": sorted({country for country, _, _, _ in expected_paths}),
        "files_checked": len(expected_paths),
        "status_counts": status_data["status_counts"],
        "problem_files": sum(len(items) for statuses in problem_by_country.values() for items in statuses.values()),
        "missing_files": sum(len(statuses.get("missing_file", [])) for statuses in problem_by_country.values()),
        "missing_by_country": {
            c: [item["path"] for item in statuses.get("missing_file", [])] for c, statuses in problem_by_country.items()
        },
        "problem_by_country": problem_by_country,
        "config_errors": config_errors,
    }

    if args.output_format == "json":
        print(json.dumps(summary, ensure_ascii=False))
        return 0

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
