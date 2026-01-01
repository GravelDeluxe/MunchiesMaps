# Baden-Württemberg GeoJSON

- Contains points of interest for Baden-Württemberg, exported from automated Overpass Turbo queries.
- Each category is stored as <category>.geojson using the manifest-driven set: fuel, supermarkets, drinking_water, burger_king, mcdonalds, toilets_public, vending_snacks.
- Some categories may be missing when no data is available; this is expected.
- Files are consumed directly by the web map; regenerate via ../../fetch_data/ instead of editing by hand.
