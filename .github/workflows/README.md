# Workflows

Automation for keeping GeoJSON data up to date.

- `fetch_overpass.yml` installs the fetch scripts, runs the Overpass queries, and commits regenerated data.
- The workflow can be invoked manually from GitHub Actions and also runs on its scheduled cron trigger.
- Outputs are written to `resources/geojson/` and served by the client application.
