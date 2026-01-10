# MunchiesMaps

MunchiesMaps is a lightweight, community-driven web map highlighting practical points of interest for cyclists across Germany. The map emphasizes essentials such as food, water, toilets, and other services that keep rides moving.

## ⚠️ Alpha status
This project is currently in an early **ALPHA** stage. Features, data structures, and the user interface may change at any time.

## What you can do today
- Browse an interactive map with colored markers per category.
- Filter points by **Bundesland** and **Kategorie**.
- Toggle dark mode for low-light use and a mobile-friendly layout for phones.
- Optionally filter markers by proximity to a GPX track.
- Rely on a manifest-driven data structure that keeps layers and categories organized.

## Cycling focus
The map is intended as a foundation for bicycle travel. It was initially designed around night rides and late-hour availability, but it is equally useful for daytime cycling, touring, and bikepacking.

## Data and contributions
- Data is imported automatically from Overpass Turbo and stored as GeoJSON under `resources/geojson/` using the manifest in that folder.
- Contributions that improve data quality, categories, or presentation are welcome; workflows and formats may evolve quickly while in alpha.

## Adding a new layer icon
- Open `index.html` and locate the `LAYER_ICON_CONFIG` object.
- Add a new entry keyed by the layer/category ID from the manifest (for example `bike_repair`), and set `iconClass` (Font Awesome class), `color` (hex), and optional `label`/`size` overrides.
- The new entry is automatically picked up by `getLayerMarkerIcon(...)` for map markers and by the list/popup category badges.

## Utilities
### Extract unique opening hours
Run the utility to scan all GeoJSON files for `properties.opening_hours` values and produce unique outputs:

```sh
node tools/extract_opening_hours.js
```
