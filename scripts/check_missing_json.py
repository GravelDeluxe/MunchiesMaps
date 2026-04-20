#!/usr/bin/env python3
"""Validate configured country/region/category datasets exist in resources/geojson."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

ROOT_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT_DIR / "fetch_data" / "config.yml"
RESOURCE_ROOT = ROOT_DIR / "resources" / "geojson"


def load_config(config_path: Path) -> dict[str, Any]:
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    try:
        with config_path.open("r", encoding="utf-8") as config_file:
            loaded = yaml.safe_load(config_file)
    except yaml.YAMLError as exc:
        raise ValueError(f"Failed to parse YAML from {config_path}: {exc}") from exc
    except OSError as exc:
        raise OSError(f"Failed to read config file {config_path}: {exc}") from exc

    if not isinstance(loaded, dict):
        raise ValueError(f"Invalid config format in {config_path}: expected a YAML mapping at root.")

    return loaded


def normalize_categories(raw_categories: Any) -> list[str]:
    if isinstance(raw_categories, dict):
        return [str(key).strip() for key in raw_categories.keys() if str(key).strip()]
    if isinstance(raw_categories, list):
        return [str(item).strip() for item in raw_categories if str(item).strip()]
    return []


def get_country_categories(country_cfg: dict[str, Any], global_categories: list[str]) -> list[str]:
    country_categories = normalize_categories(country_cfg.get("categories"))
    return country_categories or global_categories


def get_region_slug(region_cfg: dict[str, Any]) -> str | None:
    for key in ("region", "code", "id"):
        value = region_cfg.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().lower()

    path_value = region_cfg.get("path")
    if isinstance(path_value, str) and path_value.strip():
        return path_value.strip().split("/")[-1].lower()

    return None


def extract_region_paths_for_country(
    country_id: str,
    country_cfg: dict[str, Any],
    global_regions: list[dict[str, Any]],
) -> tuple[list[str], list[str]]:
    errors: list[str] = []

    global_paths = []
    for region in global_regions:
        if not isinstance(region, dict):
            continue
        if str(region.get("country", "")).strip().lower() != country_id:
            continue
        path_value = region.get("path")
        if isinstance(path_value, str) and path_value.strip():
            global_paths.append(path_value.strip().lower())

    if global_paths:
        return sorted(set(global_paths)), errors

    embedded_regions = country_cfg.get("regions")
    if not isinstance(embedded_regions, list) or not embedded_regions:
        if str(country_cfg.get("query_mode", "")).strip() == "country-only":
            return [f"{country_id}/{country_id}"], errors

        errors.append(
            f"Country '{country_id}' has no regions in country definition and none in top-level 'regions'."
        )
        return [], errors

    resolved: list[str] = []
    for idx, region_cfg in enumerate(embedded_regions, start=1):
        if not isinstance(region_cfg, dict):
            errors.append(f"Country '{country_id}' region #{idx} is not a mapping.")
            continue

        path_value = region_cfg.get("path")
        if isinstance(path_value, str) and path_value.strip():
            resolved.append(path_value.strip().lower())
            continue

        slug = get_region_slug(region_cfg)
        if not slug:
            errors.append(f"Country '{country_id}' region #{idx} has no usable identifier (region/code/id/path).")
            continue

        resolved.append(f"{country_id}/{slug}")

    return sorted(set(resolved)), errors


def build_expected_geojson_paths(config: dict[str, Any]) -> tuple[list[tuple[str, Path]], list[str]]:
    errors: list[str] = []
    countries_cfg = config.get("countries")
    global_regions = config.get("regions") if isinstance(config.get("regions"), list) else []

    if not isinstance(countries_cfg, dict) or not countries_cfg:
        return [], ["Config field 'countries' is missing or not a non-empty mapping."]

    global_categories = normalize_categories(config.get("categories"))
    if not global_categories:
        errors.append("Config field 'categories' is missing or empty; no expected files can be derived.")

    expected: list[tuple[str, Path]] = []

    for country_key, country_cfg in countries_cfg.items():
        if not isinstance(country_cfg, dict):
            errors.append(f"Country '{country_key}' has invalid definition (expected mapping).")
            continue

        country_id = str(country_key).strip().lower()
        if not country_id:
            errors.append("Encountered empty country id in config.")
            continue

        categories = get_country_categories(country_cfg, global_categories)
        if not categories:
            errors.append(f"Country '{country_id}' has no categories after resolution.")
            continue

        region_paths, region_errors = extract_region_paths_for_country(country_id, country_cfg, global_regions)
        errors.extend(region_errors)

        for region_path in region_paths:
            for category in categories:
                expected.append((country_id, RESOURCE_ROOT / region_path / f"{category}.geojson"))

    return expected, errors


def collect_missing_paths(expected_paths: list[tuple[str, Path]]) -> dict[str, list[Path]]:
    missing_by_country: dict[str, list[Path]] = defaultdict(list)
    for country, path in expected_paths:
        if not path.exists():
            missing_by_country[country].append(path)

    for country in list(missing_by_country.keys()):
        missing_by_country[country] = sorted(missing_by_country[country])

    return dict(sorted(missing_by_country.items()))


def print_missing_report(missing_by_country: dict[str, list[Path]]) -> None:
    total_missing = sum(len(paths) for paths in missing_by_country.values())
    print("Missing GeoJSON files (report only):")
    for country, paths in missing_by_country.items():
        print(f"\n[{country}] ({len(paths)})")
        for path in paths:
            print(f"- {path.relative_to(ROOT_DIR)}")

    print(f"\nSummary: {total_missing} missing file(s) across {len(missing_by_country)} countr(ies).")


def format_json_summary(
    expected_paths: list[tuple[str, Path]],
    missing_by_country: dict[str, list[Path]],
    config_errors: list[str],
) -> dict[str, Any]:
    countries_checked = sorted({country for country, _ in expected_paths})
    return {
        "countries_checked": countries_checked,
        "files_checked": len(expected_paths),
        "missing_files": sum(len(paths) for paths in missing_by_country.values()),
        "missing_by_country": {
            country: [str(path.relative_to(ROOT_DIR)) for path in paths]
            for country, paths in missing_by_country.items()
        },
        "config_errors": config_errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-format",
        choices=["text", "json"],
        default="text",
        help="Output format for missing file report.",
    )
    args = parser.parse_args()

    expected_paths: list[tuple[str, Path]] = []
    missing_by_country: dict[str, list[Path]] = {}
    config_errors: list[str] = []

    try:
        config = load_config(CONFIG_PATH)
        expected_paths, config_errors = build_expected_geojson_paths(config)
    except Exception as exc:  # noqa: BLE001
        print(f"Configuration/load issue detected (report only): {exc}")

    if expected_paths:
        missing_by_country = collect_missing_paths(expected_paths)

    if args.output_format == "json":
        summary = format_json_summary(expected_paths, missing_by_country, config_errors)
        print(json.dumps(summary, ensure_ascii=False))
        return 0

    if config_errors:
        print("Configuration issues detected (report only):")
        for error in config_errors:
            print(f"- {error}")

    if missing_by_country:
        print_missing_report(missing_by_country)
        checked_countries = len({country for country, _ in expected_paths})
        print(
            "Check completed successfully. Missing files were reported above. "
            f"(countries checked: {checked_countries}, files checked: {len(expected_paths)}, "
            f"missing files: {sum(len(paths) for paths in missing_by_country.values())})"
        )
        return 0

    print(
        "Check completed successfully. All expected GeoJSON files are present. "
        f"(countries checked: {len({country for country, _ in expected_paths})}, "
        f"files checked: {len(expected_paths)}, missing files: 0)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
