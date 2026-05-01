# URL state format

## Region state (v=2)

The region filter uses a compact URL state in the query string:

- `v=2`
- `s=<country-code>:<base36-bitmask>[;<country-code>:<base36-bitmask>...]`
- Example: `?v=2&s=de:8;cz:3f2`

Encoding rules:

1. Every country has a fixed region order (`REGION_ORDER` in `index.html`).
2. Active region = `1`, inactive region = `0`.
3. Bit string is converted to an integer and then to Base36.
4. Missing country entries in `s` mean default selection for that country.
5. Generated URLs only write canonical short country codes (for example `de`, `cz`, `ch`, `at`, `gb`).
6. Generated URLs omit countries whose bitmask is `0` or equal to the default selection.

## Additional share-state params

The writer omits params that match current app defaults and only writes overrides:

- `t` is omitted when theme is default light (`l`).
- `b`, `h`, `m` are omitted when they are default `0`/`false`.
- `pz` is omitted when it matches `DEFAULT_MIN_POI_ZOOM` (currently `9`).

Legacy URLs that include these params are still parsed.

## Backward compatibility and normalization

Still accepted on read:

- Current compact `v=2&s=...` URLs.
- Older legacy `states=` (and legacy `s=` list) URLs.
- Country aliases and long IDs already seen in old links (for example `de` and `germany`, `cz` and `czechia`, `gb` and `great-britain`).

If old URLs contain duplicate country aliases, values are merged safely. A `0` bitmask from one alias never overwrites a non-zero bitmask from another alias.
Example normalization:
- Input: `cz:1o;pl:pa8;czechia:1o;germany:cnc;poland:pa8`
- Output: `cz:1o;de:cnc;pl:pa8`

After parsing a legacy/expanded URL, the app normalizes it once with `history.replaceState` to the minimal canonical URL (no reload, no extra history entry).
