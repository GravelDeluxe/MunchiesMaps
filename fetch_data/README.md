# Overpass data fetch

Automation scripts for pulling OpenStreetMap data and exporting it as GeoJSON for the map runtime.

- `fetch_overpass.py` runs the Overpass queries defined in `overpass_templates.py` and writes results into `../resources/geojson/` following `config.yml`.
- Install dependencies with `pip install -r requirements.txt` and execute `python fetch_overpass.py` when regenerating data.
- Workflow configuration lives in `.github/workflows/fetch_overpass.yml`; it can be triggered manually or via its scheduled cron job.
- The scripts are for preprocessing only and are not part of the client-side application.
