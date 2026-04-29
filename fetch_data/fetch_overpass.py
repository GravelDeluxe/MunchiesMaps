"""Fetch GeoJSON data from Overpass for configured states and categories."""
from __future__ import annotations

import argparse
import csv
import json
import random
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
ARTIFACTS_DIR = ROOT_DIR / "artifacts"
FAILOVER_STATUS_CODES = {406, 429, 500, 502, 503, 504}
REQUEST_CONNECT_TIMEOUT = 20
REQUEST_READ_TIMEOUT = 90
JITTER_MIN_SECONDS = 0.5
JITTER_MAX_SECONDS = 1.5
SMOKE_TEST_RETRIES = 3
SMOKE_RETRY_JITTER_MIN_SECONDS = 1.0
SMOKE_RETRY_JITTER_MAX_SECONDS = 2.0
REQUEST_HEADERS = {
    "User-Agent": "MunchiesMaps/alpha (https://github.com/MarkusCouch/MunchiesMaps)"
}
TAG_WHITELIST: Dict[str, List[str]] = {
    "fuel": ["name", "brand", "opening_hours"],
    "supermarkets": ["name", "brand", "opening_hours"],
    "toilets_public": ["name", "opening_hours", "access"],
    "drinking_water": ["name", "access", "opening_hours", "fee", "seasonal", "operator", "indoor"],
    "fast_food": ["name", "brand", "opening_hours", "phone", "website", "operator", "brand:wikidata", "cuisine"],
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
    "accommodation": [
        "name",
        "tourism",
        "opening_hours",
        "tents",
        "phone",
        "contact:phone",
        "website",
        "contact:website",
        "check_date",
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
    "accommodation": "Accommodation",
    "bakerys_cafes": "Bakerys & Cafes",
    "kiosks": "Kiosks",
}
PHASE1_ISO_PREFERRED_COUNTRIES = {"DE", "AT", "CH", "CZ", "HR", "BA", "BG", "TR"}
PHASE1_COUNTRY_KEY_TO_ISO = {
    "germany": "DE",
    "austria": "AT",
    "switzerland": "CH",
    "czechia": "CZ",
}


class FetchRequestError(RuntimeError):
    """Structured request error with failure classification."""

    def __init__(self, message: str, *, status: str, endpoint: str | None = None, attempts: int = 0) -> None:
        super().__init__(message)
        self.status = status
        self.endpoint = endpoint
        self.attempts = attempts


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
            region_scope_strategy = normalize_text(raw_country.get("region_scope_strategy")).lower()
            if region_identifier_strategy == "iso3166-2":
                region_match_key = "ISO3166-2"
            raw_country_regions = raw_country.get("regions") or []
            if not isinstance(raw_country_regions, list):
                raise ValueError(f"Config error: countries.{country_key}.regions must be a list.")
            inferred_country_only = (
                len(raw_country_regions) == 1
                and int(raw_country_regions[0].get("admin_level", region_admin_level)) == country_admin_level
            )
            inferred_query_mode = normalize_text(raw_country.get("query_mode")).lower() or (
                "country-only" if inferred_country_only else None
            )
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
                region_scope_strategy_entry = (
                    normalize_text(raw_region.get("region_scope_strategy")).lower() or region_scope_strategy
                )
                region_admin_level_entry = int(raw_region.get("admin_level", region_admin_level))
                country_regions.append(
                    {
                        "id": region_id,
                        "label": label,
                        "region": region_slug,
                        "path": region_path,
                        "country": str(country_key),
                        "country_label": country_label,
                        "area_name": label,
                        "admin_level": region_admin_level_entry,
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
                        "region_scope_strategy": region_scope_strategy_entry or None,
                        "query_mode": inferred_query_mode,
                    }
                )

            if not raw_country_regions:
                query_mode = normalize_text(raw_country.get("query_mode")).lower() or "country-only"
                country_id = normalize_text(raw_country.get("id")) or str(country_key)
                country_region = normalize_text(raw_country.get("region")) or str(country_key)
                country_path = normalize_text(raw_country.get("path")) or get_geojson_path(
                    str(country_key), country_region
                )
                country_regions.append(
                    {
                        "id": country_id,
                        "label": country_label,
                        "region": country_region,
                        "path": country_path,
                        "country": str(country_key),
                        "country_label": country_label,
                        "area_name": country_label,
                        "admin_level": country_admin_level,
                        "region_boundary": None,
                        "region_match_key": "name",
                        "region_match_value": country_label,
                        "query_name": None,
                        "query_name_regex": None,
                        "country_iso": iso3166_1,
                        "country_admin_level": country_admin_level,
                        "country_scope_strategy": country_scope_strategy or None,
                        "region_code": str(country_key),
                        "region_iso3166_2": None,
                        "region_scope_strategy": None,
                        "query_mode": query_mode,
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
            region_iso = normalize_text(region.get("region_iso3166_2") or region.get("iso3166_2")).upper()
            if region_iso:
                region["region_iso3166_2"] = region_iso
                region["iso3166_2"] = region_iso
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
    country_iso = normalize_text(region.get("country_iso") or region.get("iso3166_1")).upper()
    if country_iso:
        return country_iso
    country_key = normalize_text(region.get("country")).lower()
    return PHASE1_COUNTRY_KEY_TO_ISO.get(country_key, "")


def get_region_iso_code(region: Dict[str, Any]) -> str:
    """Return optional ISO region code for relation lookup."""
    return normalize_text(region.get("region_iso3166_2") or region.get("iso3166_2")).upper()


def should_prefer_region_iso(region: Dict[str, Any], match_type: str) -> bool:
    """Use ISO3166-2 as preferred region matcher for configured countries."""
    if match_type != "exact":
        return False
    if get_country_iso_code(region) not in PHASE1_ISO_PREFERRED_COUNTRIES:
        return False
    return bool(get_region_iso_code(region))


def build_region_iso_regex(*iso_codes: str) -> str:
    """Build strict regex alternation for ISO3166-2 relation matching."""
    escaped = [re.escape(code) for code in iso_codes if code]
    return f"^({'|'.join(escaped)})$"


def has_country_scope(region: Dict[str, Any]) -> bool:
    """Return whether region should be resolved inside an explicit country scope."""
    region_scope_strategy = normalize_text(region.get("region_scope_strategy")).lower()
    if region_scope_strategy in {"direct-relation-only", "fi-iso3166-2-direct"}:
        return False
    return bool(get_country_query_name(region) or get_country_iso_code(region))


def build_country_scope_selector(region: Dict[str, Any], match_type: str, target_var: str) -> str | None:
    """Build country relation selector using ISO tag or name fallback."""
    country_admin_level = normalize_text(region.get("country_admin_level")) or "2"
    country_iso = get_country_iso_code(region)
    if country_iso and match_type == "exact":
        return (
            f"relation[\"boundary\"=\"administrative\"][\"admin_level\"=\"{country_admin_level}\"]"
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
    if country_iso and country_scope_strategy == "relation-iso-area" and match_type == "exact":
        return (
            f"relation[\"boundary\"=\"administrative\"][\"admin_level\"=\"{country_admin_level}\"]"
            f"[\"ISO3166-1\"=\"{overpass_escape(country_iso)}\"]->.country;\n"
            ".country map_to_area -> .countryArea;"
        )
    if country_iso and country_scope_strategy == "area-iso" and match_type == "exact":
        return (
            f"area[\"ISO3166-1\"=\"{overpass_escape(country_iso)}\"][\"admin_level\"=\"{country_admin_level}\"]"
            "[\"boundary\"=\"administrative\"]"
            "->.countryArea;"
        )
    if country_iso:
        return (
            f"relation[\"boundary\"=\"administrative\"][\"admin_level\"=\"{country_admin_level}\"]"
            f"[\"ISO3166-1\"=\"{overpass_escape(country_iso)}\"]->.countryRel;\n"
            ".countryRel map_to_area -> .countryArea;"
        )
    country_selector = build_country_scope_selector(region, match_type, ".countryRel")
    if not country_selector:
        return None
    return "\n".join([country_selector, ".countryRel map_to_area -> .countryArea;"])


def build_exact_relation_selector(name: str, admin_level: str, target_var: str, area_scope: str | None = None) -> str:
    """Build exact relation selector with optional area scope."""
    scope = f"(area.{area_scope})" if area_scope else ""
    return (
        f"relation[\"boundary\"=\"administrative\"][\"admin_level\"=\"{admin_level}\"]"
        f"[\"name\"=\"{overpass_escape(name)}\"]{scope}->{target_var};"
    )


def build_regex_relation_selector(pattern: str, admin_level: str, target_var: str, area_scope: str | None = None) -> str:
    """Build regex relation selector with optional area scope."""
    scope = f"(area.{area_scope})" if area_scope else ""
    return (
        f"relation[\"boundary\"=\"administrative\"][\"admin_level\"=\"{admin_level}\"]"
        f"[\"name\"~\"{overpass_escape(pattern)}\"]{scope}->{target_var};"
    )


def build_country_region_scope(region: Dict[str, Any], match_type: str) -> str | None:
    """Build region search area by first resolving country and then region."""
    country_selector = build_country_area_selector(region, match_type)
    if not country_selector:
        return None
    if should_prefer_region_iso(region, match_type):
        admin_level = str(region["admin_level"])
        region_iso = get_region_iso_code(region)
        region_relation_clause = (
            f"relation(area.countryArea)[\"boundary\"=\"administrative\"][\"admin_level\"=\"{overpass_escape(admin_level)}\"]"
            f"[\"ISO3166-2\"~\"{overpass_escape(build_region_iso_regex(region_iso))}\"]->.regions;"
        )
    else:
        region_selector = build_region_selector(region, match_type)
        if not region_selector:
            return None
        region_relation_clause = f"relation(area.countryArea){region_selector}->.regions;"
    return "\n".join(
        [
            country_selector,
            region_relation_clause,
            ".regions map_to_area -> .regionAreas;",
        ]
    )


def build_country_only_scope(region: Dict[str, Any], match_type: str) -> str | None:
    """Build country-only search area for countries without subregions."""
    country_selector = build_country_area_selector(region, match_type)
    if not country_selector:
        return None
    return "\n".join([country_selector, ".countryArea -> .searchArea;"])


def build_direct_region_scope(region: Dict[str, Any], match_type: str) -> str | None:
    """Build region search area by resolving the region relation directly."""
    if normalize_text(region.get("region_scope_strategy")).lower() == "fi-iso3166-2-direct":
        if match_type != "exact":
            return None
        admin_level = str(region["admin_level"])
        iso_code = normalize_text(region.get("region_iso3166_2")).upper()
        if not iso_code:
            return None
        return "\n".join(
            [
                (
                    "relation"
                    f"[\"boundary\"=\"administrative\"][\"admin_level\"=\"{overpass_escape(admin_level)}\"]"
                    f"[\"ISO3166-2\"~\"^{overpass_escape(iso_code)}$\"]->.regions;"
                ),
                ".regions map_to_area -> .regionAreas;",
            ]
        )

    region_selector = build_region_selector(region, match_type)
    if not region_selector:
        return None
    return "\n".join(
        [
            f"relation{region_selector}->.regionRel;",
            ".regionRel map_to_area -> .searchArea;",
        ]
    )


def build_region_selector(region: Dict[str, Any], match_type: str = "exact") -> str | None:
    """Build relation selector from configurable region-matching metadata."""
    admin_level = str(region["admin_level"])
    boundary = normalize_text(region.get("region_boundary"))
    match_key = normalize_text(region.get("region_match_key")) or "name"
    match_value = normalize_text(region.get("region_match_value"))
    if should_prefer_region_iso(region, match_type):
        match_key = "ISO3166-2"
        match_value = build_region_iso_regex(get_region_iso_code(region))
        match_type = "regex"
    if not match_value:
        return None
    if match_type == "regex":
        if match_key not in {"name", "ISO3166-2"}:
            return None
        if match_key == "ISO3166-2":
            match_operator = "~"
            match_literal = match_value
        else:
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


def build_query(
    region: Dict[str, Any],
    category: str,
    body: str,
    timeout: int,
    mode: str,
    match_type: str,
) -> str:
    """Construct the full Overpass query for a region and category."""
    query_body = body
    if mode == "country+region" or normalize_text(region.get("region_scope_strategy")).lower() == "fi-iso3166-2-direct":
        query_body = query_body.replace("(area.searchArea)", "(area.regionAreas)")

    if mode == "country+region":
        region_area = build_country_region_scope(region, match_type)
    elif mode == "direct-region":
        region_area = build_direct_region_scope(region, match_type)
    elif mode == "country-only":
        region_area = build_country_only_scope(region, match_type)
    else:
        raise ValueError(f"Unsupported query mode: {mode}")
    if not region_area:
        raise ValueError(f"Cannot build query scope for mode={mode}, match_type={match_type}, region={region['id']}")
    return dedent(
        f"""
        [out:json][timeout:{timeout}];
        {region_area}
        (
        {indent(query_body, '  ')}
        );
        out center tags;
        """
    ).strip()


def build_query_attempts(region: Dict[str, Any]) -> List[Dict[str, str]]:
    """Build ordered, de-duplicated query attempts for a region."""
    attempts: List[Dict[str, str]] = []
    region_match_key = normalize_text(region.get("region_match_key")) or "name"
    region_match_value = normalize_text(region.get("region_match_value")) or normalize_text(region.get("area_name"))
    query_mode = normalize_text(region.get("query_mode")).lower()

    def append_attempt(mode: str, match_type: str) -> None:
        if mode == "country-only":
            region_query = normalize_text(region.get("country_iso")) or normalize_text(region.get("country_label"))
        else:
            region_query = region_match_value if match_type == "exact" else get_region_query_regex(region)
        country_query = (
            get_country_query_name(region) if match_type == "exact" else get_country_query_regex(region)
        )
        country_scope = get_country_iso_code(region)
        if mode != "country-only" and not region_query:
            return
        if match_type == "regex" and region_match_key != "name":
            return
        if mode in {"country+region", "country-only"} and not (country_query or country_scope):
            return
        if mode == "direct-region":
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

    if query_mode == "country-only":
        append_attempt("country-only", "exact")
        if get_country_query_regex(region):
            append_attempt("country-only", "regex")
    elif has_country_scope(region):
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


def request_with_retry(
    endpoints: List[str],
    query: str,
    timeout: int,
    context: Dict[str, Any] | None = None,
    run_stats: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Send POST request to Overpass API with endpoint failover."""
    _ = timeout
    last_exc: Exception | None = None
    last_endpoint: str | None = None
    last_status = "exception"
    context = context or {}
    context_region = context.get("region", "-")
    context_category = context.get("category", "-")
    context_country = context.get("country", "-")
    context_query_attempt = context.get("query_attempt", "-")
    for endpoint_index, endpoint in enumerate(endpoints, start=1):
        if run_stats is not None:
            run_stats["total_attempts"] += 1
        last_endpoint = endpoint
        jitter = random.uniform(JITTER_MIN_SECONDS, JITTER_MAX_SECONDS)
        print(
            "[req] "
            f"Endpoint={endpoint} | Region={context_region} | Country={context_country} "
            f"| Category={context_category} | QueryAttempt={context_query_attempt} "
            f"| EndpointTry={endpoint_index}/{len(endpoints)} | jitter={jitter:.2f}s"
        )
        time.sleep(jitter)
        try:
            response = requests.post(
                endpoint,
                data={"data": query},
                headers=REQUEST_HEADERS,
                timeout=(REQUEST_CONNECT_TIMEOUT, REQUEST_READ_TIMEOUT),
            )
        except (requests.Timeout, requests.ConnectionError) as exc:
            last_exc = exc
            last_status = "timeout" if isinstance(exc, requests.Timeout) else "exception"
            print(
                "[req] "
                f"Exception={type(exc).__name__} | Endpoint={endpoint} | failover=next"
            )
            continue
        except requests.RequestException as exc:
            last_exc = exc
            last_status = "http_error"
            print(
                "[req] "
                f"Exception={type(exc).__name__} | Endpoint={endpoint} | failover=abort"
            )
            break

        if response.status_code in FAILOVER_STATUS_CODES:
            last_exc = requests.HTTPError(f"Overpass returned status {response.status_code}.")
            last_status = "http_error"
            print(
                "[req] "
                f"Status={response.status_code} | Endpoint={endpoint} | failover=next"
            )
            continue

        if response.status_code == 400:
            print("[error] Overpass HTTP 400 (Bad Request).")
            print("[error] Likely Overpass syntax error in generated query")
            print(f"[error] Full query:\n{query}")
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            last_exc = exc
            last_status = "http_error"
            print(f"[req] Exception=HTTPError | Endpoint={endpoint} | failover=next")
            continue
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
            last_status = "parse_error"
            print(f"[req] Exception=NonJsonResponse | Endpoint={endpoint} | failover=next")
            continue
        try:
            response_json = response.json()
            bytes_len = len(response.content or b"")
            print(f"[req] Success | endpoint={endpoint} | bytes={bytes_len}")
            if run_stats is not None:
                run_stats["endpoints_used"].add(endpoint)
                if endpoint_index > 1:
                    run_stats["rescued_by_failover"] += 1
            elements = response_json.get("elements", [])
            print(f"[data] Received elements={len(elements)}")
            return response_json
        except ValueError:
            last_exc = ValueError(
                "Failed to decode JSON from "
                f"{endpoint}: status={response.status_code}, content-type={content_type}, "
                f"body_prefix={text[:200]!r}"
            )
            last_status = "parse_error"
            print("[req] Exception=InvalidJSON | Endpoint={endpoint} | failover=next")
            continue

    if last_exc is None:
        raise FetchRequestError(
            "All Overpass endpoints failed. Last error: unknown.",
            status=last_status,
            endpoint=last_endpoint,
            attempts=len(endpoints),
        )
    raise FetchRequestError(
        f"All Overpass endpoints failed. Last error: {last_exc}",
        status=last_status,
        endpoint=last_endpoint,
        attempts=len(endpoints),
    )


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



def classify_geojson_file(path: Path) -> str:
    """Classify file health for selective refetch flows."""
    if not path.exists():
        return "missing_file"
    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        return "empty_file"
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return "invalid_json"
    if not isinstance(parsed, dict) or parsed.get("type") != "FeatureCollection" or not isinstance(parsed.get("features"), list):
        return "invalid_feature_collection"
    return "populated" if parsed.get("features") else "empty_feature_collection"

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
    return {normalize_filter_token(item) for item in value.split(",") if item.strip()}


def normalize_filter_token(value: Any) -> str:
    """Normalize filter tokens for case-insensitive matching."""
    return normalize_text(value).lower()


def utc_timestamp() -> str:
    """Return current UTC timestamp in ISO format."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def append_jsonl(path: Path | None, payload: Dict[str, Any]) -> None:
    """Append payload as JSONL line when a destination path is configured."""
    if path is None:
        return
    ensure_directory(path.parent)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")


def get_country_aliases(region: Dict[str, Any]) -> set[str]:
    """Return normalized aliases that identify a country."""
    aliases = {
        normalize_filter_token(region.get("country")),
        normalize_filter_token(region.get("country_label")),
        normalize_filter_token(region.get("country_iso")),
        normalize_filter_token(region.get("iso3166_1")),
    }
    country_iso = normalize_filter_token(region.get("country_iso") or region.get("iso3166_1"))
    if country_iso == "gb":
        aliases.update({"uk", "great britain"})
    return {alias for alias in aliases if alias}


def matches_country_filter(region: Dict[str, Any], country_filter: set[str]) -> bool:
    """Return whether region country matches any provided country filter token."""
    if not country_filter:
        return True
    return bool(get_country_aliases(region) & country_filter)


def get_region_aliases(region: Dict[str, Any]) -> set[str]:
    """Return normalized aliases that identify a region."""
    aliases = {
        normalize_filter_token(region.get("id")),
        normalize_filter_token(region.get("region")),
        normalize_filter_token(region.get("label")),
        normalize_filter_token(region.get("area_name")),
    }
    return {alias for alias in aliases if alias}


def matches_region_filter(region: Dict[str, Any], region_filter: set[str]) -> bool:
    """Return whether region matches any provided region filter token."""
    if not region_filter:
        return True
    return bool(get_region_aliases(region) & region_filter)


def write_json(path: Path, payload: Any) -> None:
    """Write a JSON payload with UTF-8 encoding."""
    ensure_directory(path.parent)
    with path.open("w", encoding="utf-8") as output_file:
        json.dump(payload, output_file, ensure_ascii=False, indent=2)


def write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: List[str]) -> None:
    """Write structured CSV rows."""
    ensure_directory(path.parent)
    with path.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def build_smoke_test_query() -> str:
    """Return a tiny Overpass query used to validate endpoint availability."""
    return dedent(
        """
        [out:json][timeout:25];
        relation(51477);
        out ids qt 1;
        """
    ).strip()


def smoke_test_endpoints(endpoints: List[str]) -> List[str]:
    """Run a lightweight smoke test against every configured endpoint."""
    smoke_query = build_smoke_test_query()
    healthy: List[str] = []
    for endpoint in endpoints:
        endpoint_ok = False
        for attempt in range(1, SMOKE_TEST_RETRIES + 1):
            if attempt > 1:
                jitter = random.uniform(SMOKE_RETRY_JITTER_MIN_SECONDS, SMOKE_RETRY_JITTER_MAX_SECONDS)
                print(
                    f"[smoke] retry_wait | endpoint={endpoint} | attempt={attempt}/{SMOKE_TEST_RETRIES} "
                    f"| jitter={jitter:.2f}s"
                )
                time.sleep(jitter)
            try:
                response = requests.post(
                    endpoint,
                    data={"data": smoke_query},
                    headers=REQUEST_HEADERS,
                    timeout=(REQUEST_CONNECT_TIMEOUT, REQUEST_READ_TIMEOUT),
                )
                if response.status_code in {406, 504}:
                    print(
                        f"[smoke] transient_failure | endpoint={endpoint} "
                        f"| status={response.status_code} | attempt={attempt}/{SMOKE_TEST_RETRIES}"
                    )
                    continue
                if response.status_code in FAILOVER_STATUS_CODES:
                    print(
                        f"[smoke] failed | endpoint={endpoint} "
                        f"| status={response.status_code} | attempt={attempt}/{SMOKE_TEST_RETRIES}"
                    )
                    continue
                response.raise_for_status()
                print(
                    f"[smoke] ok | endpoint={endpoint} | status={response.status_code} "
                    f"| attempt={attempt}/{SMOKE_TEST_RETRIES}"
                )
                healthy.append(endpoint)
                endpoint_ok = True
                break
            except requests.Timeout as exc:
                print(
                    f"[smoke] transient_failure | endpoint={endpoint} "
                    f"| exception={type(exc).__name__} | attempt={attempt}/{SMOKE_TEST_RETRIES}"
                )
                continue
            except requests.RequestException as exc:
                print(
                    f"[smoke] failed | endpoint={endpoint} | exception={type(exc).__name__}: {exc} "
                    f"| attempt={attempt}/{SMOKE_TEST_RETRIES}"
                )
                continue
        if not endpoint_ok:
            print(f"[smoke] unhealthy | endpoint={endpoint} | retries={SMOKE_TEST_RETRIES}")
    print(f"[smoke] healthy_endpoints={len(healthy)}/{len(endpoints)}")
    return healthy


def run(
    region_filter: set[str] | None = None,
    layer_filter: set[str] | None = None,
    country_filter: set[str] | None = None,
    verbose_query: bool = False,
    dry_run: bool = False,
    failure_log_jsonl: str | None = None,
    only_missing_or_invalid: bool = False,
) -> int:
    """Run the fetch process for all configured regions and categories."""
    region_filter = region_filter or set()
    layer_filter = layer_filter or set()
    country_filter = {normalize_filter_token(token) for token in (country_filter or set()) if token}

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
    request_delay_seconds = float(overpass_cfg.get("request_delay_seconds", 0.0))
    regions = normalize_regions(config)
    categories = config.get("categories", {}) or {}

    if not regions:
        raise ValueError("Config error: no regions configured (regions or legacy states required).")
    if not isinstance(categories, dict) or not categories:
        raise ValueError("Config error: categories must be a non-empty mapping.")

    selected_regions = [
        region
        for region in regions
        if matches_region_filter(region, region_filter)
        and matches_country_filter(region, country_filter)
    ]
    selected_categories = [
        (category, func_name)
        for category, func_name in categories.items()
        if not layer_filter or normalize_filter_token(category) in layer_filter
    ]

    matched_countries = sorted({region["country"] for region in selected_regions})
    if country_filter:
        print(f"[filter] Input countries: {', '.join(sorted(country_filter))}")
        print(
            "[filter] Resolved countries: "
            f"{', '.join(matched_countries) if matched_countries else '-'}"
        )
        print(f"[filter] Matched regions: {len(selected_regions)}")
        if not selected_regions:
            valid_country_ids = sorted({normalize_text(region.get("country")) for region in regions if region.get("country")})
            valid_country_labels = sorted(
                {normalize_text(region.get("country_label")) for region in regions if region.get("country_label")}
            )
            valid_country_iso = sorted(
                {
                    normalize_text(region.get("country_iso") or region.get("iso3166_1")).upper()
                    for region in regions
                    if normalize_text(region.get("country_iso") or region.get("iso3166_1"))
                }
            )
            raise ValueError(
                "Country filter matched no configured regions. "
                f"Input: {', '.join(sorted(country_filter))}. "
                f"Valid ids: {', '.join(valid_country_ids[:10])}. "
                f"Valid labels: {', '.join(valid_country_labels[:10])}. "
                f"Valid ISO: {', '.join(valid_country_iso[:10])}."
            )

    if region_filter and not selected_regions:
        raise ValueError(f"No regions matched --regions filter: {', '.join(sorted(region_filter))}")

    if layer_filter and not selected_categories:
        raise ValueError(f"No categories matched --layers filter: {', '.join(sorted(layer_filter))}")

    ensure_directory(RESOURCE_DIR)

    failure_log_path = Path(failure_log_jsonl).resolve() if failure_log_jsonl else None
    if failure_log_path:
        ensure_directory(failure_log_path.parent)
        failure_log_path.write_text("", encoding="utf-8")

    failures: List[Dict[str, Any]] = []
    results: List[Dict[str, Any]] = []
    def flush_artifacts() -> None:
        artifacts_failures_json = ARTIFACTS_DIR / "fetch_failures.json"
        artifacts_failures_csv = ARTIFACTS_DIR / "fetch_failures.csv"
        artifacts_results_json = ARTIFACTS_DIR / "fetch_results.json"
        summary_path = ARTIFACTS_DIR / "fetch_summary.md"
        write_json(artifacts_failures_json, failures)
        write_csv(
            artifacts_failures_csv,
            failures,
            ["country", "region", "layer", "status", "error_message", "endpoint", "attempt_count", "timestamp_utc"],
        )
        write_json(artifacts_results_json, results)
        failed_lines = "\n".join(
            f"- `{item['country']}/{item['region']}:{item['layer']}` → `{item['status']}`"
            for item in failures[:50]
        )
        summary = (
            "## Fetch Summary\n"
            f"- Successful updates: **{len(results)}**\n"
            f"- Failed updates: **{len(failures)}**\n"
            f"- Dry run: **{'yes' if dry_run else 'no'}**\n"
            + ("### Failed region/layer updates\n" + failed_lines + "\n" if failures else "No failures.\n")
        )
        summary_path.write_text(summary, encoding="utf-8")
        print(f"[artifacts] Wrote {artifacts_failures_json.relative_to(ROOT_DIR)}")
        print(f"[artifacts] Wrote {artifacts_results_json.relative_to(ROOT_DIR)}")
    run_stats: Dict[str, Any] = {
        "total_attempts": 0,
        "successful_fetches": 0,
        "failed_fetches": 0,
        "skipped_fetches": 0,
        "rescued_by_failover": 0,
        "endpoints_used": set(),
        "geojson_written": 0,
    }
    endpoints_display = ", ".join(endpoints)
    print(
        "[run] "
        f"Regions={len(selected_regions)}/{len(regions)} | Categories={len(selected_categories)}/{len(categories)} "
        f"| Countries={len({region['country'] for region in selected_regions})} | Endpoints={len(endpoints)} "
        f"| Timeout={timeout}s | Delay={request_delay_seconds}s"
    )
    print(f"[run] Endpoints: {endpoints_display}")
    healthy_endpoints = smoke_test_endpoints(endpoints)
    degraded_mode_used = False
    if not healthy_endpoints:
        degraded_mode_used = True
        print("[warn] No healthy endpoints → entering degraded mode")
        if not selected_regions or not selected_categories:
            failures.append(
                {
                    "country": "",
                    "region": "",
                    "layer": "",
                    "status": "exception",
                    "error_message": "No usable endpoints after degraded mode. Aborting.",
                    "endpoint": "",
                    "attempt_count": 0,
                    "timestamp_utc": utc_timestamp(),
                }
            )
            flush_artifacts()
            return 1
        probe_region = selected_regions[0]
        probe_category, probe_func_name = selected_categories[0]
        probe_template_func = get_category_function(probe_func_name)
        probe_body = probe_template_func()
        probe_attempts = build_query_attempts(probe_region)
        probe_success = False
        for probe_try, probe_attempt in enumerate(probe_attempts[:2], start=1):
            probe_query = build_query(
                probe_region,
                probe_category,
                probe_body,
                timeout,
                mode=probe_attempt["mode"],
                match_type=probe_attempt["match_type"],
            )
            print(
                "[degraded] probe "
                f"{probe_try}/2 | region={probe_region['id']} | category={probe_category} "
                f"| mode={probe_attempt['mode']} | match_type={probe_attempt['match_type']}"
            )
            try:
                request_with_retry(
                    endpoints,
                    probe_query,
                    timeout,
                    context={
                        "region": probe_region["id"],
                        "country": probe_region["country"],
                        "category": probe_category,
                        "query_attempt": f"degraded-{probe_try}",
                    },
                    run_stats=run_stats,
                )
                probe_success = True
                print("[degraded] probe_success=yes")
                break
            except Exception as exc:  # noqa: BLE001
                print(f"[degraded] probe_success=no | reason={type(exc).__name__}: {exc}")
        if probe_success:
            healthy_endpoints = endpoints
            print("[degraded] continuing with full endpoint list after successful probe")
        else:
            failures.append(
                {
                    "country": probe_region["country"],
                    "region": probe_region["id"],
                    "layer": probe_category,
                    "status": "exception",
                    "error_message": "No usable endpoints after degraded mode. Aborting.",
                    "endpoint": "",
                    "attempt_count": 0,
                    "timestamp_utc": utc_timestamp(),
                }
            )
            flush_artifacts()
            return 1

    for region_index, region in enumerate(selected_regions, start=1):
        print(
            f"[region] ({region_index}/{len(selected_regions)}) "
            f"id={region['id']} | country={region['country']} | label={region['label']}"
        )
        region_categories_raw = region.get("categories")
        if layer_filter:
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
        if not region_categories:
            print(f"[cat]   No categories selected for region={region['id']} after filters")
        for category_index, (category, func_name) in enumerate(region_categories, start=1):
            if only_missing_or_invalid:
                target_path = RESOURCE_DIR / str(region["path"]) / f"{category}.geojson"
                existing_status = classify_geojson_file(target_path)
                if existing_status in {"populated", "empty_feature_collection"}:
                    run_stats["skipped_fetches"] += 1
                    print(f"[skip] Existing valid file: {target_path.relative_to(ROOT_DIR)} | status={existing_status}")
                    continue
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
                completed_attempts = 0
                for attempt_index, attempt in enumerate(attempts, start=1):
                    completed_attempts = attempt_index
                    mode = attempt["mode"]
                    match_type = attempt["match_type"]
                    region_query = attempt["region_query"]
                    region_match_key = attempt.get("region_match_key") or region.get("region_match_key") or "name"
                    country_query = attempt["country_query"]
                    query = build_query(region, category, body, timeout, mode=mode, match_type=match_type)
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
                    response_json = request_with_retry(
                        healthy_endpoints,
                        query,
                        timeout,
                        context={
                            "region": region["id"],
                            "country": region["country"],
                            "category": category,
                            "query_attempt": attempt_index,
                        },
                        run_stats=run_stats,
                    )
                    elements = response_json.get("elements", [])
                    print(
                        "[result] "
                        f"country={region['country']} | region_id={region['id']} | category={category} "
                        f"| success={'yes' if bool(response_json) else 'no'} | elements={len(elements)}"
                    )
                    run_stats["successful_fetches"] += 1
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
                    run_stats["skipped_fetches"] += 1
                    print(
                        "[query] No Overpass elements returned after query attempts "
                        f"for region={region['id']} | category={category}"
                    )
                elif fallback_used:
                    print("[query] Fallback succeeded.")
                geojson = convert_to_geojson(elements, category)
                print(f"[diag] elements={len(elements)} | features={len(geojson.get('features', []))}")
                updated_file = str((RESOURCE_DIR / str(region["path"]) / f"{category}.geojson").relative_to(ROOT_DIR))
                if dry_run:
                    print(f"[dry-run] Skipping write for {updated_file}")
                else:
                    save_geojson(geojson, region, category)
                    run_stats["geojson_written"] += 1
                results.append(
                    {
                        "country": region["country"],
                        "region": region["id"],
                        "layer": category,
                        "status": "success",
                        "feature_count": len(geojson.get("features", [])),
                        "updated_file": updated_file,
                        "endpoint": endpoints_used[-1] if (endpoints_used := sorted(run_stats["endpoints_used"])) else "",
                        "attempt_count": completed_attempts,
                        "timestamp_utc": utc_timestamp(),
                    }
                )
                delay_seconds = request_delay_seconds + random.uniform(JITTER_MIN_SECONDS, JITTER_MAX_SECONDS)
                time.sleep(delay_seconds)
                print(f"[sleep] {delay_seconds:.2f}s before next request")
            except Exception as exc:  # noqa: BLE001
                endpoint = getattr(exc, "endpoint", None)
                status = "exception"
                if isinstance(exc, FetchRequestError):
                    status = exc.status
                elif isinstance(exc, requests.Timeout):
                    status = "timeout"
                elif isinstance(exc, requests.HTTPError):
                    status = "http_error"
                elif isinstance(exc, ValueError):
                    status = "parse_error"
                context_parts = [
                    f"region={region['id']}",
                    f"country={region['country']}",
                    f"category={category}",
                ]
                context = " / ".join(context_parts)
                endpoint_text = f" | endpoint={endpoint}" if endpoint else ""
                print(f"[error] {context}{endpoint_text} | {exc}")
                failures.append(
                    {
                        "country": region["country"],
                        "region": region["id"],
                        "layer": category,
                        "status": status,
                        "error_message": str(exc),
                        "endpoint": endpoint or "",
                        "attempt_count": getattr(exc, "attempts", 0),
                        "timestamp_utc": utc_timestamp(),
                    }
                )
                append_jsonl(
                    failure_log_path,
                    {
                        "country": region["country"],
                        "region_key": region["id"],
                        "region_name": region.get("label") or "",
                        "category": category,
                        "error_type": status,
                        "error_message": str(exc),
                        "endpoint": endpoint or "",
                        "timestamp": utc_timestamp(),
                    },
                )
                run_stats["failed_fetches"] += 1
                continue

    if dry_run:
        print("[dry-run] Skipping manifest write")
    else:
        save_manifest(regions, categories)

    endpoints_used = sorted(run_stats["endpoints_used"])
    print(
        "[summary] "
        f"Completed: {run_stats['successful_fetches']} successful, "
        f"{run_stats['failed_fetches']} failed, {run_stats['skipped_fetches']} skipped"
    )
    print(
        "[summary] "
        f"smoke_ok={len(healthy_endpoints)}/{len(endpoints)} "
        f"| rescued_by_failover={run_stats['rescued_by_failover']}"
    )
    print(
        "[summary] "
        f"endpoints healthy: {len(healthy_endpoints)}/{len(endpoints)}"
    )
    print(f"[summary] successful fetches: {run_stats['successful_fetches']}")
    print(f"[summary] failed fetches: {run_stats['failed_fetches']}")
    print(f"[summary] degraded mode used: {'yes' if degraded_mode_used else 'no'}")
    print(f"[summary] total_attempts={run_stats['total_attempts']}")
    print(f"[summary] endpoints_used={', '.join(endpoints_used) if endpoints_used else '-'}")
    print(f"[summary] geojson_written={run_stats['geojson_written']}")
    if run_stats["failed_fetches"] > 0:
        print(f"[summary] All endpoints failed for {run_stats['failed_fetches']} fetches")
        for failure in failures[:5]:
            print(
                "[summary] failure_example="
                f"{failure['country']}/{failure['region']}/{failure['layer']}:{failure['status']}"
            )

    flush_artifacts()

    if run_stats["successful_fetches"] == 0 and run_stats["failed_fetches"] > 0:
        print("[summary] No successful fetches -> exiting with error")
        return 1

    if failures:
        print(f"[warn] Completed with {len(failures)} failures:")
        for failure in failures:
            print(
                "[warn] "
                f"{failure['country']}/{failure['region']}:{failure['layer']} "
                f"| {failure['status']} | {failure['error_message']}"
            )
        if fail_on_error:
            return 1
        print("[warn] Best-effort mode: continuing despite failures (fail_on_error=false).")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch GeoJSON data from Overpass")
    parser.add_argument(
        "--regions",
        help="Comma-separated region IDs (example: de-berlin,cz-praha)",
    )
    parser.add_argument(
        "--categories",
        help="Comma-separated categories/layers (deprecated alias for --layers).",
    )
    parser.add_argument(
        "--layers",
        help="Comma-separated layers (example: fast_food,supermarkets)",
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
    parser.add_argument(
        "--failure-log-jsonl",
        help="Optional path to write machine-readable per-task failure JSONL records.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run fetch logic but do not write GeoJSON/manifest files.",
    )
    parser.add_argument(
        "--only-missing-or-invalid",
        action="store_true",
        help="Fetch only files that are missing/empty/invalid JSON or invalid FeatureCollection.",
    )
    args = parser.parse_args()
    layer_input = args.layers or args.categories

    try:
        exit_code = run(
            region_filter=parse_csv_filter(args.regions),
            layer_filter=parse_csv_filter(layer_input),
            country_filter=parse_csv_filter(args.countries),
            verbose_query=args.verbose_query,
            dry_run=args.dry_run,
            failure_log_jsonl=args.failure_log_jsonl,
            only_missing_or_invalid=args.only_missing_or_invalid,
        )
        if exit_code != 0:
            sys.exit(exit_code)
    except Exception as exc:  # noqa: BLE001
        print(f"[error] {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
