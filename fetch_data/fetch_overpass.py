"""Fetch GeoJSON data from Overpass for configured states and categories."""
from __future__ import annotations

import json
import re
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


def save_geojson(content: Dict[str, Any], state: str, category: str) -> None:
    """Save GeoJSON content to the resources directory."""
    target_dir = RESOURCE_DIR / state
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


def run() -> None:
    """Run the fetch process for all configured states and categories."""
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
    states = config.get("states", [])
    categories = config.get("categories", {})

    ensure_directory(RESOURCE_DIR)

    failures: List[str] = []
    endpoints_display = ", ".join(endpoints)
    print(
        "[run] "
        f"States={len(states)} | Categories={len(categories)} | Endpoints={len(endpoints)} "
        f"| Timeout={timeout}s | Delay={request_delay_seconds}s"
    )
    print(f"[run] Endpoints: {endpoints_display}")

    for state_index, state in enumerate(states, start=1):
        print(f"[state] ({state_index}/{len(states)}) Processing state: {state}")
        category_items = list(categories.items())
        for category_index, (category, func_name) in enumerate(category_items, start=1):
            template_func = get_category_function(func_name)
            print(f"[cat]   ({category_index}/{len(category_items)}) Category={category} | Template={func_name}")
            body = template_func()
            query = build_query(state, body, timeout)
            print(f"[query] Built query (chars={len(query)}, timeout={timeout}s)")
            try:
                response_json = request_with_retry(endpoints, query, timeout)
                elements = response_json.get("elements", [])
                geojson = convert_to_geojson(elements, category)
                save_geojson(geojson, state, category)
                if request_delay_seconds > 0:
                    time.sleep(request_delay_seconds)
                    print(f"[sleep] {request_delay_seconds}s before next request")
            except Exception as exc:  # noqa: BLE001
                endpoint = getattr(exc, "endpoint", None)
                attempt = getattr(exc, "attempt", None)
                context_parts = [state, category]
                context = " / ".join(context_parts)
                endpoint_text = f" | endpoint={endpoint}" if endpoint else ""
                attempt_text = f" | attempt={attempt}" if attempt else ""
                print(f"[error] {context}{endpoint_text}{attempt_text} | {exc}")
                msg = f"{context}{endpoint_text}{attempt_text} | {exc}"
                failures.append(msg)
                continue

    if failures:
        print(f"[warn] Completed with {len(failures)} failures:")
        for failure in failures:
            print(f"[warn] {failure}")
        if fail_on_error:
            raise RuntimeError("Fetch completed with failures; see log summary.")
        print("[warn] Best-effort mode: continuing despite failures (fail_on_error=false).")


def main() -> None:
    try:
        run()
    except Exception as exc:  # noqa: BLE001
        print(f"[error] {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
