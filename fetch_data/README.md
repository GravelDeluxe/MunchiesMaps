# Overpass data fetch

Automation scripts for pulling OpenStreetMap data and exporting it as GeoJSON for the map runtime.

- `fetch_overpass.py` runs the Overpass queries defined in `overpass_templates.py` and writes results into `../resources/geojson/` following `config.yml`.
- Install dependencies with `pip install -r requirements.txt` and execute `python fetch_overpass.py` when regenerating data.
- Workflow configuration lives in `.github/workflows/fetch_overpass.yml`; it can be triggered manually or via its scheduled cron job.
- The scripts are for preprocessing only and are not part of the client-side application.

## Regions config (minimal multi-country step)

- `config.yml` now uses `regions:` instead of a flat `states:` list.
- Optional: `countries:` can define country-level region matching defaults (`iso3166_1`, `region_admin_level`, optional `region_boundary`, `region_match_key`) and nested `regions` (`id` or `code`, `label`, `match_value` or `iso3166_2`).
- `region_identifier_strategy: iso3166-2` switches region lookup to `["ISO3166-2"="..."]` (used by Slovenia/Italy-style robust code-based matching).
- Each region entry contains explicit metadata: `id`, `label`, `path`, `country`, `country_label`, `area_name`, `admin_level`.
- Output folders are now taken from `path` (for example `resources/geojson/germany/berlin/`), not implicitly from the human-readable label.
- Legacy `states:` is still supported by the script for transition safety, but new config should use `regions:`.
- Naming fields are now split by purpose:
  - `label` / `country_label`: UI text only.
  - `area_name` / `country_area_name`: readable defaults.
  - `query_name` / `country_query_name`: technical Overpass exact-match names.
  - `query_name_regex` / `country_query_name_regex`: optional regex fallbacks.
- Overpass query resolution is now the same engine for all countries:
  - first `country+region` (if country query scope is configured), then direct region fallback,
  - each with exact match first and optional regex fallback second.
- Phase-1 migration note: DE/AT/CH/CZ regions now support `iso3166_2` directly in `regions:` and prefer ISO-based relation matching (`["ISO3166-2"~"..."]`) inside country scope; existing name/regex fallback remains active for non-migrated regions and countries.
- Region relation selector defaults remain backward compatible:
  - `region_match_key` defaults to `name`
  - `region_boundary` is optional (unset means no boundary filter)

## CLI filters

You can optionally limit a run:

- `--regions` comma-separated region IDs
- `--layers` comma-separated layers/categories
- `--categories` legacy alias for `--layers`
- `--countries` comma-separated country IDs
- `--dry-run` execute fetches without writing GeoJSON/manifest files
- `--verbose-query` prints the full Overpass query before each request

Examples:

- `python fetch_overpass.py --regions de-berlin,cz-praha --layers fast_food`
- `python fetch_overpass.py --countries czechia`
- `python fetch_overpass.py --countries austria`
- `python fetch_overpass.py --countries croatia`
- `python fetch_overpass.py --countries italy`
- `python fetch_overpass.py --regions cz-praha --layers fuel --verbose-query`
- `python fetch_overpass.py --countries croatia --layers fuel --verbose-query`
- `python fetch_overpass.py --regions it-25 --layers fuel --verbose-query`
- `python fetch_overpass.py --countries france --layers fuel --verbose-query`
- `python fetch_overpass.py --countries denmark --layers fuel --verbose-query`

The script writes run artifacts to `artifacts/`:

- `fetch_failures.json` / `fetch_failures.csv`: structured non-updated region/layer entries
- `fetch_results.json`: successful updates with feature counts and output files
- `fetch_summary.md`: compact summary for GitHub Actions job summaries

## Administrative boundary resolution

- Region lookups are now built via administrative **relations** and converted to queryable areas through `map_to_area`.
- Query prefix pattern:
  - `rel["boundary"="administrative"]["admin_level"="2"]["ISO3166-1"="..."]->.countryRel;`
  - `.countryRel map_to_area->.country;`
  - `area["ISO3166-1"="DK"]["admin_level"="2"]->.country;` (country-specific ISO area strategy, where configured)
  - `relation(area.country)["admin_level"="..."][optional boundary][match_key="match_value"]->.regionRel;`
  - `.regionRel map_to_area->.searchArea;`
- Category templates continue to run unchanged against `(area.searchArea)`.

- For new countries/regions, verify `admin_level` empirically with Overpass tests before adding/updating entries.
- In this project, Czech regions, Austrian regions, Croatian counties, Italian regions, French regions and Danish regions are queried with `admin_level=4`.


## Accommodation Audit & Recovery

- Audit only the `accommodation` layer across all configured regions:
  - `python artifacts/archived-scripts/audit_accommodation.py` (archiviert, nicht mehr Teil aktiver Workflows)
- Write report to custom path (or disable by passing empty):
  - `python artifacts/archived-scripts/audit_accommodation.py --json-report artifacts/accommodation_audit.json` (archiviert)
- Refetch only missing/empty/invalid files for one layer:
  - `python fetch_data/fetch_overpass.py --layers accommodation --only-missing-or-invalid`
- Country-scoped recovery example:
  - `python fetch_data/fetch_overpass.py --countries germany,austria,switzerland,czechia,italy,france,belgium,tr --layers accommodation --only-missing-or-invalid`

Notes:
- Empty `0-byte` or whitespace-only files are treated as invalid and flagged by the audit/check scripts.
- A successful Overpass response with no elements still writes a valid empty GeoJSON FeatureCollection (`{"type":"FeatureCollection","features":[]}`).
- Overpass/request/parse failures do **not** write output and therefore do not overwrite an existing valid file.

## Missing vs. Empty vs. Valid Empty GeoJSON

- `missing_file`: erwartete `.geojson` existiert nicht.
- `empty_file`: Datei ist 0 Byte oder nur Whitespace.
- `invalid_json`: Inhalt ist kein parsebares JSON.
- `invalid_feature_collection`: JSON ist keine gültige GeoJSON `FeatureCollection` mit `features`-Liste.
- `empty_feature_collection`: gültig und absichtlich leer (`{"type":"FeatureCollection","features":[]}`).

`check_missing_json.py` meldet standardmäßig nur echte Probleme (`missing_file`, `empty_file`, `invalid_json`, `invalid_feature_collection`).
Optional können auch `empty_feature_collection`-Dateien einbezogen werden:

- `python scripts/check_missing_json.py --output-format json --include-empty-feature-collections`

## Accommodation gezielt nachfetchen

- Nur Germany:
  - `python fetch_data/fetch_missing_overpass.py --countries germany`
- Nur Accommodation (direkt über den Hauptfetcher):
  - `python fetch_data/fetch_overpass.py --countries germany --layers accommodation --only-missing-or-invalid`

## Matrix-Recovery-Fetch

- `.github/workflows/fetch_missing_matrix.yml` baut die Matrix aus `problem_by_country` des JSON-Reports.
- Damit werden Länder mit fehlenden **und** defekten Dateien aufgenommen.
- Pro Matrix-Land wird `fetch_missing_overpass.py --countries <land>` ausgeführt, sodass problematische Kombinationen erneut gefetcht werden.
