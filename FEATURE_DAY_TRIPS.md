# Day Trips Feature Notes

This document describes the local fork workflow and the Day Trips changes that
currently live on `feature/day-trips`.

The upstream project should remain updateable from `MarkusCouch/MunchiesMaps`.
Keep feature work on topic branches and use fork `main` mainly for the
production image workflow.

## Branches And Remotes

- Fork: `origin` -> `https://github.com/GravelDeluxe/MunchiesMaps.git`
- Upstream: `upstream` -> `https://github.com/MarkusCouch/MunchiesMaps.git`
- Feature branch: `feature/day-trips`
- Production image branch: `main`

Production currently uses the image tag:

```text
ghcr.io/graveldeluxe/munchiesmaps:main
```

The Portainer stack is in `portainer.yaml` and exposes the app on host port
`8173`.

## Make Workflow

Run `make help` to see the available commands.

### Local Checks

```sh
make check
```

This parses the embedded JavaScript in `index.html` and runs the vendor asset
check from `package.json`.

### Local Docker Dev

```sh
make dev
```

This builds and starts the local Docker container from `compose.yaml`.

Local URL:

```text
http://localhost:8173
```

Useful related commands:

```sh
make dev-build
make dev-up
make dev-down
make dev-logs
```

### Production Info

```sh
make prod-info
```

This prints the actual production path:

```text
feature/day-trips -> main -> GitHub Actions -> ghcr.io/graveldeluxe/munchiesmaps:main -> Portainer/Watchtower
```

### Publish Feature To Production

When the feature branch is ready to use on production:

```sh
make prod-merge-feature
```

This does the following:

1. Fetches `origin`.
2. Checks out `main`.
3. Pulls `origin/main` with `--ff-only`.
4. Merges `feature/day-trips` into `main`.
5. Pushes `main` to `origin`.
6. Checks out `feature/day-trips` again.

A push to `main` triggers `.github/workflows/docker-publish.yml`, which builds
and publishes `ghcr.io/graveldeluxe/munchiesmaps:main`.

Portainer/Watchtower can then pull the updated image.

### Upstream PR Info

```sh
make pr-info
```

Use this branch as PR source:

```text
GravelDeluxe/MunchiesMaps:feature/day-trips
```

Target upstream:

```text
MarkusCouch/MunchiesMaps:main
```

It is okay if the fork's `main` also contains the feature for production image
publishing. For the upstream PR, keep using the feature branch as the source.

## Implemented Feature Changes

### Docker And Deployment

- Added lightweight nginx Docker setup.
- Added `compose.yaml` for local Docker runs.
- Added `portainer.yaml` for production via Portainer/Watchtower.
- Added GitHub Actions workflow to publish GHCR images.
- Production host port is `8173`, container port is `80`.
- Production image tag is `ghcr.io/graveldeluxe/munchiesmaps:main`.

### Day Trips Mode

- Added a separate Day Trips UI section.
- Added Day Trips controls:
  - Enable arrival badges.
  - Weekday.
  - Start time.
  - Average speed.
  - Hide entries without badges.
  - Include entries with missing opening-hour data.
- Added day arrival badges for POIs that are open at estimated arrival time.
- Arrival time is calculated from route distance and average speed when a GPX
  route is active.
- Without a GPX route, the configured start time is used.

### Opening Hours Handling

- Added fallback handling for opening-hour strings that the parser cannot fully
  evaluate.
- Fixed mixed public holiday rules such as:

```text
PH,Mo-Su 08:00-17:00
```

For normal weekday evaluation this is treated as:

```text
Mo-Su 08:00-17:00
```

This fixes kiosks and similar POIs being shown as `unknown on arrival` even
though the weekday rule is clear.

### Categories And Data

- Added `restaurants` as a supported category.
- Added restaurant mapping for UI labels, icons, GPX export metadata, and data
  fetching.
- Generated initial restaurant data for Saxony.
- Added command path for fetching remaining restaurant data via
  `fetch_data/fetch_overpass.py`.

### POI Visibility And Favorites

- Added `Show favorites`, separate from `Show favorites only`.
- `Show favorites` overlays favorite POIs onto the currently visible/filtered
  layer.
- Hidden and favorite POI state is preserved for saved routes where supported.

### GPX Name Preservation

- Imported GPX route names are preserved.
- Exported GPX files write the route name back into the GPX track name.
- Exported filenames use the imported route name.
- POI Markdown export filenames also use the imported route name.

### POI Markdown Export

- Added `Export visible POI list`.
- Export format is Markdown.
- With an active route, the export now includes all filtered route POIs instead
  of only POIs in the current map viewport.
- Category tables use:

```text
Distance | Name | Opening hours | Link
```

- A final combined table is appended with all POIs in route order:

```text
Category | Distance | Name | Opening hours | Link
```

## Useful Commands

Check current state:

```sh
make status
```

Validate before pushing:

```sh
make check
```

Push feature branch:

```sh
git push origin feature/day-trips
```

Publish to production:

```sh
make prod-merge-feature
```

Offer upstream PR:

```sh
make pr-info
```
