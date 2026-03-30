# Workflows

Automation for keeping GeoJSON data up to date.

- `fetch_overpass.yml` installs the fetch scripts, runs the Overpass queries, and writes regenerated data from `resources/geojson/`.
- The workflow can be started manually via **Actions → Fetch Overpass Data → Run workflow**.
- The existing scheduled run remains active on `0 1 1 * *` and uses defaults (no manual inputs required).

## Manual run inputs

`fetch_overpass.yml` supports optional `workflow_dispatch` inputs:

- `countries`: comma-separated country ids, e.g. `czechia`
- `regions`: comma-separated region ids, e.g. `cz-praha,cz-jihomoravsky`
- `categories`: comma-separated categories, e.g. `fuel,supermarkets`
- `commit_mode`: `pull_request` (default) or `direct_commit`

If an input is left empty, the fetch script runs without that filter.

## Common manual examples

- **Nur Tschechien**
  - `countries`: `czechia`
  - `regions`: *(empty)*
  - `categories`: *(empty)*
  - `commit_mode`: `pull_request`

- **Nur Prag testen**
  - `countries`: *(empty)*
  - `regions`: `cz-praha`
  - `categories`: *(empty)*
  - `commit_mode`: `pull_request`

- **Nur Tschechien + fuel/supermarkets**
  - `countries`: `czechia`
  - `regions`: *(empty)*
  - `categories`: `fuel,supermarkets`
  - `commit_mode`: `pull_request`

## Writeback behavior (`commit_mode`)

- `pull_request` (default): creates/updates a PR with `resources/geojson` changes.
- `direct_commit`: commits and pushes `resources/geojson` changes directly to the current branch.
- In both modes, writeback only happens when `resources/geojson` actually changed.
