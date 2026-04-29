#!/usr/bin/env python3
"""Audit accommodation GeoJSON files against configured regions."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fetch_data.fetch_overpass import load_config, normalize_regions  # noqa: E402

RESOURCE_DIR = ROOT_DIR / "resources" / "geojson"
DEFAULT_REPORT = ROOT_DIR / "artifacts" / "accommodation_audit.json"


def classify(path: Path) -> str:
    if not path.exists():
        return "missing_file"
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return "invalid_json"
    if not raw.strip():
        return "empty_file"
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return "invalid_json"
    if not isinstance(parsed, dict) or parsed.get("type") != "FeatureCollection" or not isinstance(parsed.get("features"), list):
        return "invalid_feature_collection"
    if len(parsed["features"]) == 0:
        return "empty_feature_collection"
    return "populated"


def run_audit() -> dict[str, Any]:
    config = load_config()
    regions = normalize_regions(config)
    rows: list[dict[str, Any]] = []
    by_country: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for region in regions:
        rel = Path(str(region["path"])) / "accommodation.geojson"
        abs_path = RESOURCE_DIR / rel
        status = classify(abs_path)
        row = {
            "country": region["country"],
            "region_id": region["id"],
            "region_label": region.get("label", ""),
            "region_path": str(region["path"]),
            "file": str((RESOURCE_DIR / rel).relative_to(ROOT_DIR)),
            "status": status,
        }
        rows.append(row)
        by_country[region["country"]].append(row)

    country_summary = {}
    for country, country_rows in sorted(by_country.items()):
        counts = Counter(item["status"] for item in country_rows)
        total = len(country_rows)
        bad = total - counts.get("populated", 0)
        if counts.get("populated", 0) == total:
            health = "fully_ok"
        elif counts.get("populated", 0) == 0:
            health = "completely_not_fetched"
        else:
            health = "partially_missing_or_invalid"
        country_summary[country] = {"health": health, "total_regions": total, "status_counts": dict(counts), "problem_regions": bad}

    return {
        "summary": {
            "regions_checked": len(rows),
            "status_counts": dict(Counter(item["status"] for item in rows)),
        },
        "countries": country_summary,
        "regions": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-report", default=str(DEFAULT_REPORT), help="Path to JSON report (empty to disable).")
    args = parser.parse_args()

    report = run_audit()
    print("Accommodation audit summary:")
    for status, count in sorted(report["summary"]["status_counts"].items()):
        print(f"- {status}: {count}")

    print("\nCountries:")
    for country, info in report["countries"].items():
        print(f"- {country}: {info['health']} ({info['problem_regions']} problematic of {info['total_regions']})")

    if args.json_report:
        path = Path(args.json_report)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        rel = path if path.is_absolute() else (ROOT_DIR / path)
        print(f"\nWrote report: {rel.relative_to(ROOT_DIR)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
