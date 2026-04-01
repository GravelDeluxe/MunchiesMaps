# GeoJSON structure

This folder contains the GeoJSON datasets that back the map. Data is organized per country/region, with `manifest.json` acting as the central source of truth for available regions and categories.

- Structure: `<path>/<category>.geojson` (for example, `germany/berlin/fuel.geojson` or `Berlin/fuel.geojson` during transition).
- `manifest.json` contains all region entries with `id`, `label`, `path`, `country`, `country_label`, and `bbox` so consumers can resolve the correct folders.
- Available categories are derived from `fetch_data/config.yml` and written to `manifest.json`.
- Files are generated automatically by the `fetch_data` scripts; regenerate rather than editing them manually.
- Czechia is currently included as a pilot country and is generated through the same GitHub Actions data pipeline.
