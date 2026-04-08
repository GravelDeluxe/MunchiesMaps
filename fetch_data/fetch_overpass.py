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
    countries_cfg = config.get("countries", {})
    country_regions: List[Dict[str, Any]] = []
    if isinstance(countries_cfg, dict):
        for country_key, raw_country in countries_cfg.items():
            if not isinstance(raw_country, dict):
                raise ValueError(f"Config error: countries.{country_key} must be an object.")
            iso3166_1 = normalize_text(raw_country.get("iso3166_1")).upper()
            if not iso3166_1:
                raise ValueError(f"Config error: countries.{country_key}.iso3166_1 is required.")
            country_label = normalize_text(raw_country.get("label")) or str(country_key).replace("-", " ").title()
            country_admin_level = int(raw_country.get("country_admin_level", 2))
            region_admin_level = int(raw_country.get("region_admin_level", 4))
            region_boundary = normalize_text(raw_country.get("region_boundary"))
            region_match_key = normalize_text(raw_country.get("region_match_key")) or "name"
            region_identifier_strategy = normalize_text(raw_country.get("region_identifier_strategy")).lower()
            country_scope_strategy = normalize_text(raw_country.get("country_scope_strategy")).lower()
            if region_identifier_strategy == "iso3166-2":
                region_match_key = "ISO3166-2"
            raw_country_regions = raw_country.get("regions") or []
            if not isinstance(raw_country_regions, list):
                raise ValueError(f"Config error: countries.{country_key}.regions must be a list.")
            for raw_region in raw_country_regions:
                if not isinstance(raw_region, dict):
                    raise ValueError(
                        f"Config error: each item in countries.{country_key}.regions must be an object."
                    )
                region_code = normalize_text(raw_region.get("code"))
                region_id = normalize_text(raw_region.get("id")) or region_code
                label = normalize_text(raw_region.get("label"))
                region_iso3166_2 = normalize_text(raw_region.get("iso3166_2")).upper()
                match_value = normalize_text(raw_region.get("match_value")) or region_iso3166_2
                if not region_id or not label or not match_value:
                    raise ValueError(
                        "Config error: country region entries require id/code, label and match_value/iso3166_2."
                    )
                region_slug = normalize_text(raw_region.get("region")) or region_code or region_id
                region_path = normalize_text(raw_region.get("path")) or get_geojson_path(str(country_key), region_slug)
                query_name = normalize_text(raw_region.get("query_name"))
                query_name_regex = normalize_text(raw_region.get("query_name_regex"))
                country_regions.append(
                    {
                        "id": region_id,
                        "label": label,
                        "region": region_slug,
                        "path": region_path,
                        "country": str(country_key),
                        "country_label": country_label,
                        "area_name": label,
                        "admin_level": region_admin_level,
                        "region_boundary": region_boundary or None,
                        "region_match_key": region_match_key,
                        "region_match_value": match_value,
                        "query_name": query_name or None,
                        "query_name_regex": query_name_regex or None,
                        "country_iso": iso3166_1,
                        "country_admin_level": country_admin_level,
                        "country_scope_strategy": country_scope_strategy or None,
                        "region_code": region_code or region_id,
                        "region_iso3166_2": region_iso3166_2 or None,
                    }
                )

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
            region["region_match_key"] = normalize_text(region.get("region_match_key")) or "name"
            region["region_match_value"] = normalize_text(region.get("region_match_value")) or normalize_text(
                region.get("area_name")
            )
            region_boundary = normalize_text(region.get("region_boundary"))
            region["region_boundary"] = region_boundary or None
            country_iso = normalize_text(region.get("country_iso")).upper()
            if country_iso:
                region["country_iso"] = country_iso
            if "region" not in region or not str(region["region"]).strip():
                configured_path = str(region["path"])
                if "/" in configured_path:
                    region["region"] = configured_path.split("/", 1)[1]
                elif "-" in configured_path:
                    region["region"] = configured_path.split("-", 1)[1]
                else:
                    region["region"] = slugify(str(region["label"]))
            region["path"] = get_geojson_path(str(region["country"]), str(region["region"]))
            regions.append(region)
        return [*regions, *country_regions]

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
                    "region": slugify(state_name),
                    "path": get_geojson_path("germany", slugify(state_name)),
                    "country": "germany",
                    "country_label": "Germany",
                    "area_name": state_name,
                    "admin_level": 4,
                }
            )
        return [*regions, *country_regions]

    return country_regions


def overpass_escape(value: str) -> str:
    """Escape Overpass string literals."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def get_region_query_name(region: Dict[str, Any]) -> str:
    """Return technical region name for exact query matching."""
    if normalize_text(region.get("region_match_key")) != "name":
        return ""
    return (
        normalize_text(region.get("query_name"))
        or normalize_text(region.get("region_match_value"))
        or normalize_text(region.get("area_name"))
    )


def get_country_query_name(region: Dict[str, Any]) -> str:
    """Return technical country name for exact query matching."""
    return normalize_text(region.get("country_query_name")) or normalize_text(region.get("country_area_name"))


def get_region_query_regex(region: Dict[str, Any]) -> str:
    """Return optional region regex fallback pattern."""
    configured_regex = normalize_text(region.get("query_name_regex"))
    if configured_regex:
        return configured_regex

    area_name = normalize_text(region.get("area_name"))
    if "/" not in area_name:
        return ""

    variants: List[str] = []
    for candidate in [area_name, *area_name.split("/")]:
        normalized_candidate = normalize_text(candidate)
        if normalized_candidate and normalized_candidate not in variants:
            variants.append(normalized_candidate)
    if not variants:
        return ""
    escaped_variants = [re.escape(value) for value in variants]
    return f"^({'|'.join(escaped_variants)})$"


def get_country_query_regex(region: Dict[str, Any]) -> str:
    """Return optional country regex fallback pattern."""
    return normalize_text(region.get("country_query_name_regex"))


def get_country_iso_code(region: Dict[str, Any]) -> str:
    """Return optional ISO country code for country relation lookup."""
    return normalize_text(region.get("country_iso") or region.get("iso3166_1")).upper()


def has_country_scope(region: Dict[str, Any]) -> bool:
    """Return whether region should be resolved inside an explicit country scope."""
    return bool(get_country_query_name(region) or get_country_iso_code(region))


def build_country_scope_selector(region: Dict[str, Any], match_type: str, target_var: str) -> str | None:
    """Build country relation selector using ISO tag or name fallback."""
    country_admin_level = normalize_text(region.get("country_admin_level")) or "2"
    country_iso = get_country_iso_code(region)
    if country_iso and match_type == "exact":
        return (
            f"rel[\"boundary\"=\"administrative\"][\"admin_level\"=\"{country_admin_level}\"]"
            f"[\"ISO3166-1\"=\"{overpass_escape(country_iso)}\"]->{target_var};"
        )

    country_query = (
        get_country_query_name(region) if match_type == "exact" else get_country_query_regex(region)
    )
    if not country_query:
        return None
    selector_builder = build_exact_relation_selector if match_type == "exact" else build_regex_relation_selector
    return selector_builder(country_query, country_admin_level, target_var)


def build_country_area_selector(region: Dict[str, Any], match_type: str) -> str | None:
    """Build country area selector with ISO-first strategy."""
    country_admin_level = normalize_text(region.get("country_admin_level")) or "2"
    country_iso = get_country_iso_code(region)
    country_scope_strategy = normalize_text(region.get("country_scope_strategy")).lower()
    if country_iso and country_scope_strategy == "area-iso" and match_type == "exact":
        return (
            f"area[\"ISO3166-1\"=\"{overpass_escape(country_iso)}\"][\"admin_level\"=\"{country_admin_level}\"]"
            "->.country;"
        )
    if country_iso:
        return (
            f"rel[\"boundary\"=\"administrative\"][\"admin_level\"=\"{country_admin_level}\"]"
            f"[\"ISO3166-1\"=\"{overpass_escape(country_iso)}\"]->.countryRel;\n"
            ".countryRel map_to_area->.country;"
        )
    country_selector = build_country_scope_selector(region, match_type, ".countryRel")
    if not country_selector:
        return None
    return "\n".join([country_selector, ".countryRel map_to_area->.country;"])


def build_exact_relation_selector(name: str, admin_level: str, target_var: str, area_scope: str | None = None) -> str:
    """Build exact relation selector with optional area scope."""
    scope = f"(area.{area_scope})" if area_scope else ""
    return (
        f"rel[\"boundary\"=\"administrative\"][\"admin_level\"=\"{admin_level}\"]"
        f"[\"name\"=\"{overpass_escape(name)}\"]{scope}->{target_var};"
    )


def build_regex_relation_selector(pattern: str, admin_level: str, target_var: str, area_scope: str | None = None) -> str:
    """Build regex relation selector with optional area scope."""
    scope = f"(area.{area_scope})" if area_scope else ""
    return (
        f"rel[\"boundary\"=\"administrative\"][\"admin_level\"=\"{admin_level}\"]"
        f"[\"name\"~\"{overpass_escape(pattern)}\"]{scope}->{target_var};"
    )


def build_country_region_scope(region: Dict[str, Any], match_type: str) -> str | None:
    """Build region search area by first resolving country and then region."""
    country_selector = build_country_area_selector(region, match_type)
    region_selector = build_region_selector(region, match_type)
    if not country_selector or not region_selector:
        return None
    return "\n".join(
        [
            country_selector,
            f"relation(area.country){region_selector}->.regionRel;",
            ".regionRel map_to_area->.searchArea;",
        ]
    )


def build_direct_region_scope(region: Dict[str, Any], match_type: str) -> str | None:
    """Build region search area by resolving the region relation directly."""
    region_selector = build_region_selector(region, match_type)
    if not region_selector:
        return None
    return "\n".join(
        [
            f"relation{region_selector}->.regionRel;",
            ".regionRel map_to_area->.searchArea;",
        ]
    )


def build_region_selector(region: Dict[str, Any], match_type: str = "exact") -> str | None:
    """Build relation selector from configurable region-matching metadata."""
    admin_level = str(region["admin_level"])
    boundary = normalize_text(region.get("region_boundary"))
    match_key = normalize_text(region.get("region_match_key")) or "name"
    match_value = normalize_text(region.get("region_match_value"))
    if not match_value:
        return None
    if match_type == "regex":
        if match_key != "name":
            return None
        region_regex = get_region_query_regex(region)
        if not region_regex:
            return None
        match_operator = "~"
        match_literal = region_regex
    else:
        match_operator = "="
        match_literal = match_value

    filters = [f"[\"admin_level\"=\"{overpass_escape(admin_level)}\"]"]
    if boundary:
        filters.append(f"[\"boundary\"=\"{overpass_escape(boundary)}\"]")
    filters.append(
        f"[\"{overpass_escape(match_key)}\"{match_operator}\"{overpass_escape(match_literal)}\"]"
    )
    return "".join(filters)


def build_query(region: Dict[str, Any], body: str, timeout: int, mode: str, match_type: str) -> str:
    """Construct the full Overpass query for a region and category."""
    if mode == "country+region":
        region_area = build_country_region_scope(region, match_type)
    elif mode == "direct-region":
        region_area = build_direct_region_scope(region, match_type)
    else:
        raise ValueError(f"Unsupported query mode: {mode}")
    if not region_area:
        raise ValueError(f"Cannot build query scope for mode={mode}, match_type={match_type}, region={region['id']}")
    return dedent(
        f"""
        [out:json][timeout:{timeout}];
        {region_area}
        (
        {indent(body, '  ')}
        );
        out center tags;
        """
    ).strip()


def build_query_attempts(region: Dict[str, Any]) -> List[Dict[str, str]]:
    """Build ordered, de-duplicated query attempts for a region."""
    attempts: List[Dict[str, str]] = []
    region_match_key = normalize_text(region.get("region_match_key")) or "name"
    region_match_value = normalize_text(region.get("region_match_value")) or normalize_text(region.get("area_name"))

    def append_attempt(mode: str, match_type: str) -> None:
        region_query = region_match_value if match_type == "exact" else get_region_query_regex(region)
        country_query = (
            get_country_query_name(region) if match_type == "exact" else get_country_query_regex(region)
        )
        country_scope = get_country_iso_code(region)
        if not region_query:
            return
        if match_type == "regex" and region_match_key != "name":
            return
        if mode == "country+region" and not (country_query or country_scope):
            return
        if mode != "country+region":
            country_query = ""
            country_scope = ""
        attempts.append(
            {
                "mode": mode,
                "match_type": match_type,
                "region_query": region_query,
                "region_match_key": region_match_key,
                "country_query": country_query,
                "country_scope": country_scope,
            }
        )

    if has_country_scope(region):
        append_attempt("country+region", "exact")
        if get_region_query_regex(region) or get_country_query_regex(region):
            append_attempt("country+region", "regex")
        append_attempt("direct-region", "exact")
        if get_region_query_regex(region):
            append_attempt("direct-region", "regex")
    else:
        append_attempt("direct-region", "exact")
        if get_region_query_regex(region):
            append_attempt("direct-region", "regex")

    unique_attempts: List[Dict[str, str]] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for attempt in attempts:
        key = (
            attempt["mode"],
            attempt["match_type"],
            attempt["region_query"],
            attempt.get("region_match_key", ""),
            attempt["country_query"],
            attempt["country_scope"],
        )
        if key in seen:
            continue
        seen.add(key)
        unique_attempts.append(attempt)
    return unique_attempts


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

            if response.status_code == 400:
                print("[error] Overpass HTTP 400 (Bad Request).")
                print("[error] Likely Overpass syntax error in generated query")
                print(f"[error] Full query:\n{query}")
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


def get_geojson_path(country: str, region: str) -> str:
    """Build canonical country/region path for a region dataset."""
    return f"{country}/{region}"


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
                "region": region.get("region"),
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
        region_categories_raw = region.get("categories")
        if category_filter:
            region_categories = list(selected_categories)
        elif isinstance(region_categories_raw, list) and region_categories_raw:
            allowed_region_categories = {
                str(item).strip() for item in region_categories_raw if str(item).strip()
            }
            region_categories = [
                (category, func_name)
                for category, func_name in selected_categories
                if category in allowed_region_categories
            ]
        else:
            region_categories = list(selected_categories)
        for category_index, (category, func_name) in enumerate(region_categories, start=1):
            template_func = get_category_function(func_name)
            print(
                f"[cat]   ({category_index}/{len(region_categories)}) "
                f"Region={region['id']} | Country={region['country']} | Category={category} | Template={func_name}"
            )
            body = template_func()
            try:
                attempts = build_query_attempts(region)
                if not attempts:
                    raise ValueError(f"No valid query attempts for region={region['id']}")

                elements: List[Dict[str, Any]] = []
                fallback_used = False
                for attempt_index, attempt in enumerate(attempts, start=1):
                    mode = attempt["mode"]
                    match_type = attempt["match_type"]
                    region_query = attempt["region_query"]
                    region_match_key = attempt.get("region_match_key") or region.get("region_match_key") or "name"
                    country_query = attempt["country_query"]
                    query = build_query(region, body, timeout, mode=mode, match_type=match_type)
                    prefix = "[query]" if attempt_index == 1 else "[query] fallback ->"
                    print(
                        f"{prefix} country={region['country']} | region_id={region['id']} | region_label={region['label']} "
                        f"| region_match_key={region_match_key} | region_match_value={region_query} "
                        f"| admin_level={region['admin_level']} | boundary={region.get('region_boundary') or '-'} "
                        f"| country_query={country_query or '-'} "
                        f"| mode={mode} | match_type={match_type} | category={category}"
                    )
                    print(f"[query] Built query (chars={len(query)}, timeout={timeout}s)")
                    if verbose_query:
                        print(f"[query] Full query:\n{query}")
                    response_json = request_with_retry(endpoints, query, timeout)
                    elements = response_json.get("elements", [])
                    print(
                        "[result] "
                        f"country={region['country']} | region_id={region['id']} | category={category} "
                        f"| success={'yes' if bool(response_json) else 'no'} | elements={len(elements)}"
                    )
                    if elements:
                        break
                    if attempt_index < len(attempts):
                        fallback_used = True
                        next_attempt = attempts[attempt_index]
                        print(
                            "[query] No elements returned; considering fallback "
                            f"to mode={next_attempt['mode']} | match_type={next_attempt['match_type']}"
                        )

                if not elements:
                    print(
                        "[query] No Overpass elements returned after query attempts "
                        f"for region={region['id']} | category={category}"
                    )
                elif fallback_used:
                    print("[query] Fallback succeeded.")
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
