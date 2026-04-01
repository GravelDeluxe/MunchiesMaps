# Overpass data fetch

Automation scripts for pulling OpenStreetMap data and exporting it as GeoJSON for the map runtime.

- `fetch_overpass.py` runs the Overpass queries defined in `overpass_templates.py` and writes results into `../resources/geojson/` following `config.yml`.
- Install dependencies with `pip install -r requirements.txt` and execute `python fetch_overpass.py` when regenerating data.
- Workflow configuration lives in `.github/workflows/fetch_overpass.yml`; it can be triggered manually or via its scheduled cron job.
- The scripts are for preprocessing only and are not part of the client-side application.

## Regions config (minimal multi-country step)

- `config.yml` now uses `regions:` instead of a flat `states:` list.
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

## CLI filters

You can optionally limit a run:

- `--regions` comma-separated region IDs
- `--categories` comma-separated categories
- `--countries` comma-separated country IDs
- `--verbose-query` prints the full Overpass query before each request

Examples:

- `python fetch_overpass.py --regions de-berlin,cz-praha --categories fast_food`
- `python fetch_overpass.py --countries czechia`
- `python fetch_overpass.py --regions cz-praha --categories fuel --verbose-query`

## Administrative boundary resolution

- Region lookups are now built via administrative **relations** and converted to queryable areas through `map_to_area`.
- Query prefix pattern:
  - `rel["boundary"="administrative"]["admin_level"="..."]["name"="..."]->.regionRel;`
  - `.regionRel map_to_area->.searchArea;`
- Category templates continue to run unchanged against `(area.searchArea)`.

- For new countries/regions, verify `admin_level` empirically with Overpass tests before adding/updating entries.
- In this project, Czech regions are queried with `admin_level=4` to match the desired kraj-level boundaries.
