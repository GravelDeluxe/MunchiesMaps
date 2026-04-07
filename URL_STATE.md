# URL state format

## Region state (v=2)

The region filter uses a compact URL state in the query string:

- `v=2`
- `s=<country-code>:<base36-bitmask>[;<country-code>:<base36-bitmask>...]`
- Example: `?v=2&s=de:zzzz;cz:3f2;ch:1a8;at:2k`

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
