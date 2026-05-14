# Repository Guidance

This repository is the GravelDeluxe fork of `MarkusCouch/MunchiesMaps`.
Develop here in a way that keeps the fork easy to update from the original
project and suitable for upstream pull requests.

## Git Workflow

- `origin` should point to `https://github.com/GravelDeluxe/MunchiesMaps.git`.
- `upstream` should point to `https://github.com/MarkusCouch/MunchiesMaps.git`.
- Keep feature work on topic branches, for example `feature/day-trips`.
- Before larger work, fetch upstream and rebase or merge deliberately so this
  fork can continue to receive new features and fixes from the original app.
- Prefer small, reviewable commits grouped by purpose.
- Do not rewrite or restructure large parts of the app unless the task clearly
  requires it. A smaller patch is easier to rebase and easier to offer back as a
  pull request.

## Updateability Rule

For all development, preserve the base app's ability to track and absorb changes
from `MarkusCouch/MunchiesMaps`. Treat the fork as an extension layer on top of
the original project, not as a permanent hard fork.

Concretely:

- Reuse existing app patterns before introducing new architecture.
- Keep broad formatting churn out of functional changes.
- Avoid moving large blocks of `index.html` unless necessary.
- Isolate new feature logic where practical, especially for Day Trips behavior.
- Keep generated data and vendored assets separate from handwritten app changes.
- Document any intentional divergence from upstream.

## Project Shape

- The app is mostly static HTML/CSS/JavaScript centered around `index.html`.
- Supporting JavaScript currently lives in `js/`.
- Static resources and generated GeoJSON data live under `resources/`.
- Data-fetching and validation helpers live under `fetch_data/` and `scripts/`.
- Third-party browser assets are vendored under `vendor/` and are synced through
  the npm scripts in `package.json`.

## Local Development

- Check `package.json` before assuming a framework or dev server exists.
- Current npm scripts are vendor-related, not a full app build pipeline.
- Docker is the preferred production path for this fork because the production
  box runs Portainer and Watchtower.
- Keep Docker lightweight and optional: nginx serves the static files, with no
  Node build step unless the app later needs one.
- The local/production Docker host port is `8173`; the container serves HTTP on
  port `80`.
- Publish production images as `ghcr.io/graveldeluxe/munchiesmaps:main`.
- `portainer.yaml` is the Portainer/Watchtower stack template.
- This workspace currently has legacy `docker-compose`; `docker compose` may
  not be available locally.
- Prefer a static-server setup for quick local edits unless the app gains a real
  build step.

## Day Trips Direction

The planned extension is a separate Day Trips mode/menu that should work beside
the existing night-focused features.

Initial scope should stay focused:

- User enters ride start day of week.
- User enters ride start time.
- User enters average speed.
- If a GPX route is loaded, estimate POI arrival time from distance along route.
- Apply day-trip badges to POIs that are open when the rider is expected to
  arrive.

Keep surface-aware and gradient-aware travel-time calculation as a later phase
unless the user explicitly asks to implement it now.

## Verification

- Run lightweight checks available in the repo before finishing work.
- For JavaScript changes, at minimum run syntax checks where practical.
- For UI work, start a local server and inspect the app in a browser when the
  task affects visible behavior.
- If a check cannot be run, state that clearly in the final response.
