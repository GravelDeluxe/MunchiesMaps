#!/usr/bin/env python3
"""Fail on empty or invalid GeoJSON files."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GEOJSON_ROOT = ROOT / "resources" / "geojson"


def main() -> int:
    bad: list[str] = []
    for path in sorted(GEOJSON_ROOT.rglob("*.geojson")):
        rel = path.relative_to(ROOT)
        raw = path.read_text(encoding="utf-8")
        if not raw.strip():
            bad.append(f"{rel}: empty_file")
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            bad.append(f"{rel}: invalid_json")
            continue
        if not isinstance(data, dict) or data.get("type") != "FeatureCollection" or not isinstance(data.get("features"), list):
            bad.append(f"{rel}: invalid_feature_collection")
    if bad:
        print("GeoJSON integrity check failed:")
        for item in bad:
            print(f"- {item}")
        return 1
    print("GeoJSON integrity check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
