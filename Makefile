SHELL := /bin/sh

APP_NAME := munchiesmaps
HOST_PORT := 8173
IMAGE := ghcr.io/graveldeluxe/munchiesmaps
PROD_TAG := main
FEATURE ?= feature/day-trips
COMPOSE ?= docker-compose

.PHONY: help status check dev dev-build dev-up dev-down dev-logs prod-info prod-merge-feature prod-push-main pr-info

help:
	@printf '%s\n' \
		'MunchiesMaps workflow targets:' \
		'' \
		'  make status              Show current git branch/status/remotes.' \
		'  make check               Parse embedded JavaScript and check vendored assets.' \
		'  make dev                 Build and run the local Docker container on port 8173.' \
		'  make dev-build           Build the local Docker image from compose.yaml.' \
		'  make dev-up              Start the local Docker container from compose.yaml.' \
		'  make dev-down            Stop the local Docker container.' \
		'  make dev-logs            Follow local container logs.' \
		'  make prod-info           Show the production image/Portainer setup.' \
		'  make prod-merge-feature  Merge FEATURE into main and push main for GHCR build.' \
		'  make prod-push-main      Push main; GitHub Actions publishes :main.' \
		'  make pr-info             Show the PR source/target to offer upstream.' \
		'' \
		'Variables:' \
		'  FEATURE=feature/day-trips' \
		'  COMPOSE=docker-compose'

status:
	git status --short --branch
	git remote -v
	git log --oneline --decorate -5

check:
	node -e "const fs=require('fs'),vm=require('vm'); const html=fs.readFileSync('index.html','utf8'); const re=/<script([^>]*)>([\s\S]*?)<\/script>/gi; let m,count=0; while ((m=re.exec(html))) { const attrs=m[1]||''; if (/type=[\"']application\/ld\+json[\"']/i.test(attrs)) continue; const body=m[2].trim(); if (!body) continue; new vm.Script(body); count++; } console.log('embedded js scripts parse ok:', count);"
	npm run check-vendor

dev: dev-build dev-up
	@printf 'Local app: http://localhost:%s\n' '$(HOST_PORT)'

dev-build:
	$(COMPOSE) -f compose.yaml build

dev-up:
	$(COMPOSE) -f compose.yaml up -d

dev-down:
	$(COMPOSE) -f compose.yaml down

dev-logs:
	$(COMPOSE) -f compose.yaml logs -f

prod-info:
	@printf '%s\n' \
		'Production is wired to Portainer/Watchtower via portainer.yaml:' \
		'  image: $(IMAGE):$(PROD_TAG)' \
		'  port:  $(HOST_PORT):80' \
		'' \
		'GitHub Actions publishes $(IMAGE):$(PROD_TAG) on pushes to main.' \
		'So production update path is: merge feature -> push main -> GHCR image -> Watchtower.'

prod-merge-feature:
	git fetch origin
	git checkout main
	git pull --ff-only origin main
	git merge --no-ff $(FEATURE)
	git push origin main
	git checkout $(FEATURE)
	@printf '%s\n' 'Pushed main. Check GitHub Actions: Publish Docker image.'

prod-push-main:
	git checkout main
	git push origin main
	git checkout $(FEATURE)
	@printf '%s\n' 'Pushed main. Check GitHub Actions: Publish Docker image.'

pr-info:
	@printf '%s\n' \
		'For an upstream PR, keep using the feature branch as PR source:' \
		'  source: GravelDeluxe/MunchiesMaps:$(FEATURE)' \
		'  target: MarkusCouch/MunchiesMaps:main' \
		'' \
		'Your fork main can still be used for production image publishing.'
