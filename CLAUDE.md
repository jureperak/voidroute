# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Voidroute is an infrastructure-as-code repository managing a self-hosted services stack. It orchestrates containerized applications (Jellyfin, qBittorrent, Sonarr, AdGuard, PostgreSQL) behind a Caddy reverse proxy, with a Homepage dashboard as the unified entrypoint.

There is no application source code, build system, or test suite — this is purely infrastructure configuration.

## Architecture

**Caddy** is the reverse proxy handling TLS, subdomain routing, and IP-based access control (local network 192.168.8.0/24 + VPN subnet). **Homepage** provides a dashboard with service cards and system widgets, using Docker socket for service discovery. All other services (Jellyfin, qBittorrent, Sonarr, AdGuard) run in Docker containers on a shared `entrypoint` network, with only Caddy exposed on ports 80/443.

**Template system**: All runtime configuration uses `.template` files with `${VAR_NAME}` placeholders, substituted at deploy time via `envsubst`. Sensitive values (API keys, passwords) come from GitHub Actions secrets; non-sensitive config from GitHub Actions variables.

## Deployment

Deployments run via GitHub Actions on a **self-hosted runner** in the Production environment.

- **`entrypoint_deploy.yml`**: Deploys Caddy + Homepage. Triggers on push to `infra/caddy/**` or manual dispatch. Runs `envsubst` on templates, copies configs to `$SERVER_BASE_PATH`, and recreates Docker containers.
- **`release-the-elephant.yml`**: Deploys PostgreSQL. Manual dispatch only.

There are no local build or deploy commands — everything runs through GitHub Actions workflows.

## Key Conventions

- Configuration templates live under `infra/` and use the `.template` extension
- The `infra/nginx/` directory is legacy — Caddy is the active reverse proxy
- Services use codenames: Tortuga (Jellyfin), Blackpearl (qBittorrent)
- Access control is enforced at the Caddy layer with graceful error handling for 502/503/504
