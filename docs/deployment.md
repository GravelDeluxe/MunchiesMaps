# Docker Deployment

Munchies Maps is currently a static app, so the Docker setup is intentionally
thin: an nginx image serves the repository files.

## Local Container

```bash
docker compose up --build
```

If the Compose plugin is not installed, use the legacy command:

```bash
docker-compose up --build
```

Open:

```text
http://localhost:8173
```

The container listens on port `80`; the host port is `8173`.

## Portainer

Use `portainer.yaml` as a Portainer stack template, or create an equivalent
stack manually.

Use the image:

```text
ghcr.io/graveldeluxe/munchiesmaps:main
```

Expose:

```text
8173:80
```

The Portainer stack includes the Watchtower label:

```text
com.centurylinklabs.watchtower.enable=true
```

## Publishing Images

The `Publish Docker image` GitHub Actions workflow publishes images to:

```text
ghcr.io/graveldeluxe/munchiesmaps:main
```

It runs on pushes to `main`, version tags, and manual dispatches.

Keep Docker as optional deployment support. The base app should remain usable as
a static site without Docker so this fork can stay easy to update from upstream.
