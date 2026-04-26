# URL state format

## Region state (v=2)

The region filter uses a compact URL state in the query string:

- `v=2`
- `s=<country-code>:<base36-bitmask>[;<country-code>:<base36-bitmask>...]`
- Example: `?v=2&s=de:zzzz;cz:3f2;ch:1a8;at:2k;hr:8v1;it:lf9`

Additional share-state params (optional):

- `pz=<number>`: minimum zoom level required to show POIs (default `10` if omitted).

Encoding rules:

1. Every country has a fixed region order (`REGION_ORDER` in `index.html`).
2. Active region = `1`, inactive region = `0`.
3. Bit string is converted to an integer and then to Base36.
4. Missing country entries in `s` mean default selection for that country.

## Backward compatibility

Legacy links using `states=` (or previous `s=` list format) are still accepted.
On load, legacy region state is parsed and immediately migrated to `v=2&s=...` using `history.replaceState` (no reload, no extra history entry).
Legacy region parameters are removed from the URL after migration.

## Offline / PWA smoke test

1. Open the app online once.
2. Activate a few regions/layers so GeoJSON files are requested.
3. In DevTools, verify service worker registration under **Application → Service Workers**.
4. In DevTools, set **Network → Offline**.
5. Open a new browser tab.
6. Open the same Munchies Maps URL including query parameters.
7. Expected behavior:
   - App shell (`index.html`) still loads.
   - UI renders and stays usable.
   - Previously loaded GeoJSON files can be served from cache.
   - Never-loaded regions fail gracefully while offline.
8. Go online again and confirm fresh data loads normally.
