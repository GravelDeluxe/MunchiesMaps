# MunchiesMaps by nightrides.cc

## Overview
MunchiesMaps is a lightweight, community-driven web map highlighting practical points of interest for cyclists across Germany. The map emphasizes essentials such as food, water, toilets, and other services that keep rides moving.

The map is intended as a foundation for bicycle travel and planning adventures on the bike. It was initially designed around nightrides and late-hour availability, but it is equally useful for daytime cycling, touring, and bikepacking.

## Features
- Browse an interactive map with colored markers per category.
- Filter points by **Bundesland** and **Kategorie**.
- Toggle dark mode for low-light use and a mobile-friendly layout for phones.
- Optionally filter markers by proximity to a GPX track.
- Rely on a manifest-driven data structure that keeps layers and categories organized.

## Usage
### Adding a new layer icon
- Open `../index.html` and locate the `LAYER_ICON_CONFIG` object.
- Add a new entry keyed by the layer/category ID from the manifest (for example `bike_repair`), and set `iconClass` (Font Awesome class), `color` (hex), and optional `label`/`size` overrides.
- The new entry is automatically picked up by `getLayerMarkerIcon(...)` for map markers and by the list/popup category badges.

### Utilities
#### Extract unique opening hours
Run the utility to scan all GeoJSON files for `properties.opening_hours` values and produce unique outputs:

```sh
node ../tools/extract_opening_hours.js
```

## Project Status
This project is currently in an early **ALPHA** stage. Features, data structures, and the user interface may change at any time.

## Contributing
- Data is imported automatically from Overpass Turbo and stored as GeoJSON under `../resources/geojson/` using the manifest in that folder.
- Contributions that improve data quality, categories, or presentation are welcome; workflows and formats may evolve quickly while in alpha.

## Credits
### OpenStreetMap data & licensing
All geographic data shown on this map is derived from **OpenStreetMap** and its contributors.

© OpenStreetMap contributors  
OpenStreetMap® is open data, licensed under the **Open Data Commons Open Database License (ODbL) v1.0**.

This means:
- The underlying map data originates from OpenStreetMap and is freely available.
- Any derived datasets (such as the GeoJSON files in this repository) are subject to the ODbL.
- If the data is redistributed or modified, appropriate attribution and share-alike obligations apply.

More information:
- https://www.openstreetmap.org/copyright
- https://opendatacommons.org/licenses/odbl/

MunchiesMaps does not claim ownership over the underlying OpenStreetMap data and exists as a visualization and filtering layer on top of it.
