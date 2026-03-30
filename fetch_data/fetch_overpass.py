"""Fetch GeoJSON data from Overpass for configured states and categories."""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import unicodedata
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
TAG_WHITELIST: Dict[str, List[str]] = {
    "fuel": ["name", "brand", "opening_hours"],
    "supermarkets": ["name", "brand", "opening_hours"],
    "toilets_public": ["name", "opening_hours", "access"],
    "drinking_water": ["name", "access", "opening_hours", "fee", "seasonal", "operator", "indoor"],
    "fast_food": ["name", "brand", "opening_hours", "phone", "website", "operator", "brand:wikidata"],
    "vending_snacks": ["name", "opening_hours", "vending", "products", "brand", "operator"],
    "shelters": [
        "name",
        "access",
        "shelter_type",
        "covered",
        "bench",
        "table",
        "capacity",
        "fee",
        "operator",
        "description",
        "url",
    ],
    "bakerys_cafes": ["name", "brand", "opening_hours", "takeaway", "outdoor_seating"],
    "kiosks": ["name", "brand", "opening_hours"],
}
CATEGORY_LABELS: Dict[str, str] = {
    "fuel": "Fuel stations",
    "supermarkets": "Supermarkets",
    "toilets_public": "Public toilets",
    "drinking_water": "Drinking water",
    "fast_food": "Fast-Food",
    "vending_snacks": "Vending (Snacks & Drinks)",
    "shelters": "Shelters",
    "bakerys_cafes": "Bakerys & Cafes",
    "kiosks": "Kiosks",
}


def normalize_text(value: Any) -> str:
    """Normalize text for comparisons."""
    if value is None:
        return ""
    return str(value).strip()


def detect_fast_food_chain(tags: Dict[str, Any]) -> str:
    """Determine fast-food chain for supported brands."""
    wikidata = normalize_text(tags.get("brand:wikidata"))
    if wikidata == "Q38076":
        return "mcdonalds"
    if wikidata == "Q177054":
        return "burger_king"

    candidates = [
        normalize_text(tags.get("brand")),
        normalize_text(tags.get("operator")),
        normalize_text(tags.get("name")),
    ]
    for value in candidates:
        if not value:
            continue
        if re.search(r"\bMcDonald'?s\b", value, re.IGNORECASE):
            return "mcdonalds"
        if re.search(r"\bBurger\s*King\b|\bBurgerKing\b", value, re.IGNORECASE):
            return "burger_king"
    return "unknown"


def load_config() -> Dict[str, Any]:
    """Load YAML configuration."""
    with CONFIG_PATH.open("r", encoding="utf-8") as config_file:
        return yaml.safe_load(config_file)


def slugify(value: str) -> str:
    """Create a stable ASCII slug."""
    normalized = unicodedata.normalize("NFKD", value)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_only.lower()).strip("-")
    return slug or "region"


def normalize_regions(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Read regions from modern config and keep compatibility with legacy states list."""
    raw_regions = config.get("regions")
    if isinstance(raw_regions, list) and raw_regions:
        regions: List[Dict[str, Any]] = []
        for raw_region in raw_regions:
            if not isinstance(raw_region, dict):
                raise ValueError("Config error: each item in regions must be an object.")
            required_fields = [
                "id",
                "label",
                "path",
                "country",
                "country_label",
                "area_name",
                "admin_level",
            ]
            missing = [field for field in required_fields if field not in raw_region]
            if missing:
                raise ValueError(
                    f"Config error: region is missing required field(s): {', '.join(missing)}"
                )
            region = dict(raw_region)
            region["admin_level"] = int(region["admin_level"])
            regions.append(region)
        return regions

    raw_states = config.get("states", [])
    if isinstance(raw_states, list) and raw_states:
        regions = []
        for state in raw_states:
            if not isinstance(state, str) or not state.strip():
                raise ValueError("Config error: each item in states must be a non-empty string.")
            state_name = state.strip()
            regions.append(
                {
                    "id": f"de-{slugify(state_name)}",
                    "label": state_name,
                    "path": state_name,
                    "country": "germany",
                    "country_label": "Germany",
                    "area_name": state_name,
                    "admin_level": 4,
                }
            )
        return regions

    return []


def build_query(region: Dict[str, Any], body: str, timeout: int, use_legacy_area: bool = False) -> str:
    """Construct the full Overpass query for a region and category."""
    area_name = region["area_name"]
    admin_level = str(region["admin_level"])
    if use_legacy_area:
        region_area = (
            f"area[\"name\"=\"{area_name}\"][\"boundary\"=\"administrative\"][\"admin_level\"=\"{admin_level}\"]->.searchArea;"
        )
    else:
        region_area = "\n".join(
            [
                f"rel[\"boundary\"=\"administrative\"][\"admin_level\"=\"{admin_level}\"][\"name\"=\"{area_name}\"]->.regionRel;",
                "map_to_area.regionRel->.searchArea;",
            ]
        )
    return dedent(
        f"""
        [out:json][timeout:{timeout}];
        {region_area}
        (
        {indent(body, '  ')}
        );
        out center qt;
        """
    ).strip()


def request_with_retry(endpoints: List[str], query: str, timeout: int) -> Dict[str, Any]:
    """Send POST request to Overpass API with exponential backoff and failover."""
    last_exc: Exception | None = None
    last_endpoint: str | None = None
    last_attempt: int | None = None
    for endpoint in endpoints:
        attempt = 0
        connect_timeout = 10
        read_timeout = min(120, timeout + 30)
        while True:
            attempt += 1
            last_endpoint = endpoint
            last_attempt = attempt
            print(f"[req] Endpoint={endpoint} | Attempt={attempt}/{MAX_RETRIES}")
            try:
                response = requests.post(
                    endpoint,
                    data={"data": query},
                    timeout=(connect_timeout, read_timeout),
                )
            except requests.RequestException as exc:
                last_exc = exc
                if attempt > MAX_RETRIES:
                    break
                backoff = INITIAL_BACKOFF * (BACKOFF_FACTOR ** (attempt - 1))
                print(f"[req] Exception={type(exc).__name__} | retry in {backoff:.1f}s")
                time.sleep(backoff)
                continue

            if response.status_code in RETRYABLE_STATUS_CODES:
                if attempt > MAX_RETRIES:
                    last_exc = requests.HTTPError(
                        f"Overpass returned status {response.status_code} after {MAX_RETRIES} retries."
                    )
                    break
                backoff = INITIAL_BACKOFF * (BACKOFF_FACTOR ** (attempt - 1))
                print(f"[req] Status={response.status_code} | retry in {backoff:.1f}s")
                time.sleep(backoff)
                continue

            response.raise_for_status()
            text = response.text or ""
            stripped = text.lstrip()
            content_type = response.headers.get("Content-Type", "")
            is_json = stripped.startswith("{") or stripped.startswith("[")
            if not is_json and "application/json" in content_type.lower() and stripped:
                is_json = True
            if not is_json:
                last_exc = ValueError(
                    "Non-JSON response from "
                    f"{endpoint}: status={response.status_code}, content-type={content_type}, "
                    f"body_prefix={text[:200]!r}"
                )
                if attempt > MAX_RETRIES:
                    break
                backoff = INITIAL_BACKOFF * (BACKOFF_FACTOR ** (attempt - 1))
                print(f"[req] Exception=NonJsonResponse | retry in {backoff:.1f}s")
                time.sleep(backoff)
                continue
            try:
                response_json = response.json()
                bytes_len = len(response.content or b"")
                print(f"[req] Success | endpoint={endpoint} | bytes={bytes_len}")
                elements = response_json.get("elements", [])
                print(f"[data] Received elements={len(elements)}")
                return response_json
            except ValueError as exc:
                last_exc = ValueError(
                    "Failed to decode JSON from "
                    f"{endpoint}: status={response.status_code}, content-type={content_type}, "
                    f"body_prefix={text[:200]!r}"
                )
                if attempt > MAX_RETRIES:
                    break
                backoff = INITIAL_BACKOFF * (BACKOFF_FACTOR ** (attempt - 1))
                print(f"[req] Exception={type(exc).__name__} | retry in {backoff:.1f}s")
                time.sleep(backoff)
                continue

        print(f"[warn] Endpoint {endpoint} failed after {MAX_RETRIES} retries; trying next endpoint...")

    if last_exc is None:
        raise RuntimeError("All Overpass endpoints failed. Last error: unknown.")
    error = RuntimeError(f"All Overpass endpoints failed. Last error: {last_exc}")
    setattr(error, "endpoint", last_endpoint)
    setattr(error, "attempt", last_attempt)
    raise error


def filter_tags_for_category(tags: Dict[str, Any], category: str) -> Dict[str, Any]:
    """Filter tags based on allowed list for a category."""
    allowed = TAG_WHITELIST.get(category)
    if not allowed:
        return {}
    return {k: tags[k] for k in allowed if k in tags}


def element_to_feature(element: Dict[str, Any], category: str) -> Dict[str, Any] | None:
    """Convert a single Overpass element to a GeoJSON feature."""
    properties = {"id": element.get("id"), "osm_type": element.get("type")}
    all_tags = element.get("tags") or {}
    properties.update(filter_tags_for_category(all_tags, category))
    if category == "fast_food":
        properties["chain"] = detect_fast_food_chain(all_tags)

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


def convert_to_geojson(elements: Iterable[Dict[str, Any]], category: str) -> Dict[str, Any]:
    """Convert Overpass elements list into a GeoJSON FeatureCollection."""
    features: List[Dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    element_count = 0
    chain_counts = {"mcdonalds": 0, "burger_king": 0, "unknown": 0}
    for element in elements:
        element_count += 1
        if category == "bakerys_cafes":
            osm_type = element.get("type")
            osm_id = element.get("id")
            if osm_type and osm_id is not None:
                key = (str(osm_type), int(osm_id))
                if key in seen:
                    continue
                seen.add(key)
        feature = element_to_feature(element, category)
        if feature:
            features.append(feature)
            if category == "fast_food":
                chain = feature["properties"].get("chain", "unknown")
                if chain in chain_counts:
                    chain_counts[chain] += 1
                else:
                    chain_counts["unknown"] += 1
    if category == "fast_food":
        print(
            "[geo] Converted elements="
            f"{element_count} -> features={len(features)} "
            f"(mcd={chain_counts['mcdonalds']}, bk={chain_counts['burger_king']}, "
            f"unknown={chain_counts['unknown']})"
        )
    else:
        print(f"[geo] Converted elements={element_count} -> features={len(features)}")
    return {"type": "FeatureCollection", "features": features}


def ensure_directory(path: Path) -> None:
    """Create directory if it does not already exist."""
    path.mkdir(parents=True, exist_ok=True)


def has_geojson_files(path: Path) -> bool:
    """Check whether directory exists and contains GeoJSON files."""
    if not path.is_dir():
        return False
    return any(file_path.suffix == ".geojson" for file_path in path.iterdir())


def resolve_region_data_path(region: Dict[str, Any]) -> str:
    """Resolve data path with compatibility fallback to legacy label directories."""
    configured_path = str(region["path"])
    configured_dir = RESOURCE_DIR / configured_path
    if has_geojson_files(configured_dir):
        return configured_path

    legacy_path = str(region["label"])
    legacy_dir = RESOURCE_DIR / legacy_path
    if legacy_path != configured_path and has_geojson_files(legacy_dir):
        return legacy_path

    return configured_path


def iter_geojson_coordinates(coords: Any) -> Iterable[List[float]]:
    """Yield all coordinate pairs found in a GeoJSON coordinate structure."""
    if not isinstance(coords, list):
        return
    if len(coords) >= 2 and all(isinstance(value, (int, float)) for value in coords[:2]):
        yield [float(coords[0]), float(coords[1])]
        return
    for child in coords:
        if isinstance(child, list):
            yield from iter_geojson_coordinates(child)


def compute_bbox_from_geojson_dir(region_path: str) -> List[float] | None:
    """Compute bbox from all features found in region GeoJSON files."""
    region_dir = RESOURCE_DIR / region_path
    if not region_dir.is_dir():
        return None

    min_lon = min_lat = max_lon = max_lat = None
    has_points = False

    for geojson_file in sorted(region_dir.glob("*.geojson")):
        try:
            with geojson_file.open("r", encoding="utf-8") as input_file:
                data = json.load(input_file)
        except (OSError, ValueError) as exc:
            print(f"[manifest] Skipping invalid GeoJSON {geojson_file}: {exc}")
            continue
        features = data.get("features") if isinstance(data, dict) else None
        if not isinstance(features, list):
            continue
        for feature in features:
            if not isinstance(feature, dict):
                continue
            geometry = feature.get("geometry")
            if not isinstance(geometry, dict):
                continue
            for lon, lat in iter_geojson_coordinates(geometry.get("coordinates")):
                has_points = True
                min_lon = lon if min_lon is None else min(min_lon, lon)
                min_lat = lat if min_lat is None else min(min_lat, lat)
                max_lon = lon if max_lon is None else max(max_lon, lon)
                max_lat = lat if max_lat is None else max(max_lat, lat)

    if not has_points:
        return None
    return [min_lon, min_lat, max_lon, max_lat]


def category_label(category_id: str) -> str:
    """Resolve user-facing category label."""
    if category_id in CATEGORY_LABELS:
        return CATEGORY_LABELS[category_id]
    return category_id.replace("_", " ").strip().title()


def build_manifest(regions: List[Dict[str, Any]], categories: Dict[str, str]) -> Dict[str, Any]:
    """Build manifest content from config and currently available GeoJSON files."""
    manifest_regions: List[Dict[str, Any]] = []
    for region in regions:
        region_path = resolve_region_data_path(region)
        manifest_regions.append(
            {
                "id": region["id"],
                "label": region["label"],
                "path": region_path,
                "country": region["country"],
                "country_label": region["country_label"],
                "bbox": compute_bbox_from_geojson_dir(region_path),
            }
        )

    manifest_categories = [
        {"id": category_id, "label": category_label(category_id)}
        for category_id in categories.keys()
    ]

    return {
        "regions": manifest_regions,
        "bundeslaender": manifest_regions,
        "categories": manifest_categories,
    }


def save_manifest(regions: List[Dict[str, Any]], categories: Dict[str, str]) -> None:
    """Write manifest.json from config and currently available GeoJSON files."""
    ensure_directory(RESOURCE_DIR)
    manifest_path = RESOURCE_DIR / "manifest.json"
    manifest = build_manifest(regions, categories)
    print(f"[manifest] Writing {manifest_path.relative_to(ROOT_DIR)}")
    with manifest_path.open("w", encoding="utf-8") as manifest_file:
        json.dump(manifest, manifest_file, ensure_ascii=False, indent=2)
    print(f"[manifest] Saved (regions={len(manifest['regions'])}, categories={len(manifest['categories'])})")


def save_geojson(content: Dict[str, Any], region: Dict[str, Any], category: str) -> None:
    """Save GeoJSON content to the resources directory."""
    target_dir = RESOURCE_DIR / str(region["path"])
    ensure_directory(target_dir)
    target_path = target_dir / f"{category}.geojson"
    print(f"[file] Writing {target_path.relative_to(ROOT_DIR)}")
    with target_path.open("w", encoding="utf-8") as geojson_file:
        json.dump(content, geojson_file, ensure_ascii=False, indent=2)
    size_bytes = target_path.stat().st_size
    print(f"[file] Saved (size={size_bytes} bytes)")


def get_category_function(name: str):
    """Resolve template function by name from overpass_templates."""
    func = getattr(overpass_templates, name, None)
    if func is None:
        raise ValueError(f"No template function defined for category '{name}'")
    return func


def parse_csv_filter(value: str | None) -> set[str]:
    """Parse a comma-separated filter value."""
    if value is None:
        return set()
    return {item.strip() for item in value.split(",") if item.strip()}


def run(
    region_filter: set[str] | None = None,
    category_filter: set[str] | None = None,
    country_filter: set[str] | None = None,
    verbose_query: bool = False,
) -> None:
    """Run the fetch process for all configured regions and categories."""
    region_filter = region_filter or set()
    category_filter = category_filter or set()
    country_filter = country_filter or set()

    config = load_config()
    overpass_cfg = config.get("overpass", {})
    endpoints = overpass_cfg.get("endpoints") or overpass_cfg.get("endpoint")
    if isinstance(endpoints, str):
        endpoints = [endpoints]
    if (
        not isinstance(endpoints, list)
        or not endpoints
        or not all(isinstance(endpoint, str) and endpoint.strip() for endpoint in endpoints)
    ):
        raise ValueError(
            "Config error: overpass.endpoints must be a non-empty list of URLs (or legacy overpass.endpoint string)."
        )
    timeout = int(overpass_cfg.get("timeout", 180))
    fail_on_error = bool(overpass_cfg.get("fail_on_error", False))
    request_delay_seconds = float(overpass_cfg.get("request_delay_seconds", 0.3))
    regions = normalize_regions(config)
    categories = config.get("categories", {}) or {}

    if not regions:
        raise ValueError("Config error: no regions configured (regions or legacy states required).")
    if not isinstance(categories, dict) or not categories:
        raise ValueError("Config error: categories must be a non-empty mapping.")

    selected_regions = [
        region
        for region in regions
        if (not region_filter or region["id"] in region_filter)
        and (not country_filter or region["country"] in country_filter)
    ]
    selected_categories = [
        (category, func_name)
        for category, func_name in categories.items()
        if not category_filter or category in category_filter
    ]

    ensure_directory(RESOURCE_DIR)

    failures: List[str] = []
    endpoints_display = ", ".join(endpoints)
    print(
        "[run] "
        f"Regions={len(selected_regions)}/{len(regions)} | Categories={len(selected_categories)}/{len(categories)} "
        f"| Countries={len({region['country'] for region in selected_regions})} | Endpoints={len(endpoints)} "
        f"| Timeout={timeout}s | Delay={request_delay_seconds}s"
    )
    print(f"[run] Endpoints: {endpoints_display}")

    for region_index, region in enumerate(selected_regions, start=1):
        print(
            f"[region] ({region_index}/{len(selected_regions)}) "
            f"id={region['id']} | country={region['country']} | label={region['label']}"
        )
        for category_index, (category, func_name) in enumerate(selected_categories, start=1):
            template_func = get_category_function(func_name)
            print(
                f"[cat]   ({category_index}/{len(selected_categories)}) "
                f"Region={region['id']} | Country={region['country']} | Category={category} | Template={func_name}"
            )
            body = template_func()
            query = build_query(region, body, timeout)
            print(
                "[query] "
                f"region={region['id']} | country={region['country']} | area={region['area_name']} "
                f"| level={region['admin_level']} | category={category}"
            )
            print(f"[query] Built query (chars={len(query)}, timeout={timeout}s)")
            if verbose_query:
                print(f"[query] Full query:\n{query}")
            try:
                response_json = request_with_retry(endpoints, query, timeout)
                elements = response_json.get("elements", [])
                if len(elements) == 0:
                    print(
                        "No Overpass elements returned for "
                        f"region={region['id']}, area_name={region['area_name']}, "
                        f"admin_level={region['admin_level']}, category={category}"
                    )
                    fallback_query = build_query(region, body, timeout, use_legacy_area=True)
                    print(
                        "[query] Fallback to legacy area selector "
                        f"for region={region['id']} | category={category}"
                    )
                    if verbose_query:
                        print(f"[query] Full fallback query:\n{fallback_query}")
                    response_json = request_with_retry(endpoints, fallback_query, timeout)
                    elements = response_json.get("elements", [])
                geojson = convert_to_geojson(elements, category)
                print(f"[diag] elements={len(elements)} | features={len(geojson.get('features', []))}")
                save_geojson(geojson, region, category)
                if request_delay_seconds > 0:
                    time.sleep(request_delay_seconds)
                    print(f"[sleep] {request_delay_seconds}s before next request")
            except Exception as exc:  # noqa: BLE001
                endpoint = getattr(exc, "endpoint", None)
                attempt = getattr(exc, "attempt", None)
                context_parts = [
                    f"region={region['id']}",
                    f"country={region['country']}",
                    f"category={category}",
                ]
                context = " / ".join(context_parts)
                endpoint_text = f" | endpoint={endpoint}" if endpoint else ""
                attempt_text = f" | attempt={attempt}" if attempt else ""
                print(f"[error] {context}{endpoint_text}{attempt_text} | {exc}")
                msg = f"{context}{endpoint_text}{attempt_text} | {exc}"
                failures.append(msg)
                continue

    save_manifest(regions, categories)

    if failures:
        print(f"[warn] Completed with {len(failures)} failures:")
        for failure in failures:
            print(f"[warn] {failure}")
        if fail_on_error:
            raise RuntimeError("Fetch completed with failures; see log summary.")
        print("[warn] Best-effort mode: continuing despite failures (fail_on_error=false).")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch GeoJSON data from Overpass")
    parser.add_argument(
        "--regions",
        help="Comma-separated region IDs (example: de-berlin,cz-praha)",
    )
    parser.add_argument(
        "--categories",
        help="Comma-separated categories (example: fast_food,supermarkets)",
    )
    parser.add_argument(
        "--countries",
        help="Comma-separated country IDs (example: germany,czechia)",
    )
    parser.add_argument(
        "--verbose-query",
        action="store_true",
        help="Print full Overpass query text before each request.",
    )
    args = parser.parse_args()

    try:
        run(
            region_filter=parse_csv_filter(args.regions),
            category_filter=parse_csv_filter(args.categories),
            country_filter=parse_csv_filter(args.countries),
            verbose_query=args.verbose_query,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[error] {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
