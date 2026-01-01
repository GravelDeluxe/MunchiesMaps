# Resources

This directory stores static assets and generated geospatial data consumed by the web map.

- GeoJSON exports live in `geojson/` and are grouped by Bundesland and category.
- Files are produced by the scripts in `../fetch_data/` and loaded directly by the client in `index.html`.
- Because the contents are generated, edit the source scripts rather than the GeoJSON files when changes are needed.
