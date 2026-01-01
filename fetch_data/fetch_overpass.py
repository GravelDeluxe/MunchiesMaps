"""Fetch GeoJSON data from Overpass for configured states and categories."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from textwrap import dedent, indent
from typing import Any, Dict, Iterable, List

import requests
import yaml

import overpass_templates

CONFIG_PATH = Path(__file__).resolve().parent / "config.yml"
ROOT_DIR = Path(__file__).resolve().parent.parent
RESOURCE_DIR = ROOT_DIR / "resources" / "geojson"
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
MAX_RETRIES = 5
INITIAL_BACKOFF = 1.0
BACKOFF_FACTOR = 2


def load_config() -> Dict[str, Any]:
    """Load YAML configuration."""
    with CONFIG_PATH.open("r", encoding="utf-8") as config_file:
        return yaml.safe_load(config_file)


def build_query(state: str, body: str, timeout: int) -> str:
    """Construct the full Overpass query for a state and category."""
    state_area = (
        f"area[\"name\"=\"{state}\"][\"boundary\"=\"administrative\"][\"admin_level\"=\"4\"]->.searchArea;"
    )
    return dedent(
        f"""
        [out:json][timeout:{timeout}];
        {state_area}
        (
        {indent(body, '  ')}
        );
        out center;
        """
    ).strip()


def request_with_retry(endpoint: str, query: str, timeout: int) -> Dict[str, Any]:
    """Send POST request to Overpass API with exponential backoff."""
    attempt = 0
    while True:
        attempt += 1
        try:
            response = requests.post(
                endpoint,
                data={"data": query},
                timeout=timeout + 30,
            )
        except requests.RequestException as exc:
            if attempt > MAX_RETRIES:
                raise RuntimeError(f"Request failed after {attempt - 1} retries: {exc}") from exc
            backoff = INITIAL_BACKOFF * (BACKOFF_FACTOR ** (attempt - 1))
            print(f"[warn] Request error '{exc}', retrying in {backoff:.1f}s (attempt {attempt}/{MAX_RETRIES})")
            time.sleep(backoff)
            continue

        if response.status_code in RETRYABLE_STATUS_CODES:
            if attempt > MAX_RETRIES:
                response.raise_for_status()
            backoff = INITIAL_BACKOFF * (BACKOFF_FACTOR ** (attempt - 1))
            print(
                f"[warn] Overpass returned status {response.status_code}, retrying in {backoff:.1f}s "
                f"(attempt {attempt}/{MAX_RETRIES})"
            )
            time.sleep(backoff)
            continue

        response.raise_for_status()
        return response.json()


def element_to_feature(element: Dict[str, Any]) -> Dict[str, Any] | None:
    """Convert a single Overpass element to a GeoJSON feature."""
    properties = {"id": element.get("id"), "osm_type": element.get("type")}
    properties.update(element.get("tags", {}))

    geometry = None
    if element.get("type") == "node" and {"lat", "lon"}.issubset(element):
        geometry = {
            "type": "Point",
            "coordinates": [element["lon"], element["lat"]],
        }
    elif "center" in element:
        center = element["center"]
        geometry = {
            "type": "Point",
            "coordinates": [center["lon"], center["lat"]],
        }
    elif "geometry" in element:
        coords = [[point["lon"], point["lat"]] for point in element["geometry"]]
        geometry = {
            "type": "LineString",
            "coordinates": coords,
        }

    if geometry is None:
        return None

    return {
        "type": "Feature",
        "geometry": geometry,
        "properties": properties,
    }


def convert_to_geojson(elements: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Convert Overpass elements list into a GeoJSON FeatureCollection."""
    features: List[Dict[str, Any]] = []
    for element in elements:
        feature = element_to_feature(element)
        if feature:
            features.append(feature)
    return {"type": "FeatureCollection", "features": features}


def ensure_directory(path: Path) -> None:
    """Create directory if it does not already exist."""
    path.mkdir(parents=True, exist_ok=True)


def save_geojson(content: Dict[str, Any], state: str, category: str) -> None:
    """Save GeoJSON content to the resources directory."""
    target_dir = RESOURCE_DIR / state
    ensure_directory(target_dir)
    target_path = target_dir / f"{category}.geojson"
    with target_path.open("w", encoding="utf-8") as geojson_file:
        json.dump(content, geojson_file, ensure_ascii=False, indent=2)
    print(f"[info] Saved {category} for {state} -> {target_path.relative_to(ROOT_DIR)}")


def get_category_function(name: str):
    """Resolve template function by name from overpass_templates."""
    func = getattr(overpass_templates, name, None)
    if func is None:
        raise ValueError(f"No template function defined for category '{name}'")
    return func


def run() -> None:
    """Run the fetch process for all configured states and categories."""
    config = load_config()
    overpass_cfg = config.get("overpass", {})
    endpoint = overpass_cfg.get("endpoint")
    timeout = int(overpass_cfg.get("timeout", 180))
    states = config.get("states", [])
    categories = config.get("categories", {})

    ensure_directory(RESOURCE_DIR)

    for state in states:
        for category, func_name in categories.items():
            template_func = get_category_function(func_name)
            body = template_func()
            query = build_query(state, body, timeout)
            print(f"[info] Requesting {category} in {state}")
            response_json = request_with_retry(endpoint, query, timeout)
            elements = response_json.get("elements", [])
            geojson = convert_to_geojson(elements)
            save_geojson(geojson, state, category)


def main() -> None:
    try:
        run()
    except Exception as exc:  # noqa: BLE001
        print(f"[error] {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
