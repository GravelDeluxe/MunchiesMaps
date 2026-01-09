# GeoJSON structure

This folder contains the GeoJSON datasets that back the map. Data is organized per Bundesland, with categories defined in `manifest.json` acting as the single source of truth.

- Structure: `<Bundesland>/<category>.geojson` (e.g., `Berlin/fuel.geojson`).
- Available categories follow the manifest and include fuel, supermarkets, drinking_water, fast_food, toilets_public, and vending_snacks.
- Files are generated automatically by the `fetch_data` scripts; regenerate rather than editing them manually.
