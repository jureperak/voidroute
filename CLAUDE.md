# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Voidroute is an infrastructure-as-code repository managing a self-hosted media and services stack. It orchestrates containerized applications behind a Caddy reverse proxy, with a Homepage dashboard as the unified entrypoint.

There is no application source code, build system, or test suite — this is purely infrastructure configuration.

## Services

| Service | Purpose | Subdomain |
|---|---|---|
| Caddy | Reverse proxy, TLS, access control | — |
| Homepage | Dashboard | homepage.* |
| Jellyfin | Media server | jellyfin.* |
| qBittorrent | Torrent client | qbittorrent.* |
| Sonarr | TV show management | sonarr.* |
| Radarr | Movie management | radarr.* |
| Prowlarr | Indexer management | prowlarr.* |
| Bazarr | Subtitle management | bazarr.* |
| Jellyseerr | Request/discovery UI | jellyseerr.* |
| Flaresolverr | Cloudflare solver for Prowlarr | (internal only) |
| Portainer | Docker management UI | portainer.* |
| Docker socket proxy | Read-only Docker API for Homepage | (internal only) |
| AdGuard Home | DNS/ad blocking (external) | adguard.* |
| PostgreSQL | Database (separate workflow) | — |

## Architecture

**Caddy** handles TLS, subdomain routing, and IP-based access control (local network 192.168.8.0/24 + VPN subnet). All services run on a shared `voidroute` Docker network, with only Caddy exposed on ports 80/443. PostgreSQL joins the same network and publishes 5432 on `127.0.0.1` only.

A separate `homepage-internal` network (internal, `172.30.255.0/29`) connects Homepage, Caddy and `dockerproxy`. Caddy's admin API binds only to its static IP there (`172.30.255.2:2019`), and Homepage reaches Docker via `dockerproxy:2375` (containers read-only) instead of mounting `docker.sock`.

**Folder layout** follows TRaSH Guides conventions:
```
${MEDIA_ROOT}/
├── config/{jellyfin,qbittorrent,sonarr,radarr,prowlarr,bazarr,jellyseerr}/
└── data/
    ├── downloads/torrents/{movies,series}/
    └── media/{movies,series}/
```

qBittorrent, Sonarr and Radarr mount `${MEDIA_ROOT}/data` as a single `/data` volume so imports use hardlinks and atomic moves. Do not split it into separate `/downloads` and `/media` mounts — hardlinks/renames fail across bind mounts and fall back to copying.

**Template system**: `.template` files use `${VAR_NAME}` placeholders, substituted at deploy time via `envsubst`. Sensitive values (API keys, passwords) come from GitHub Actions secrets; non-sensitive config from GitHub Actions variables.

## Deployment

Deployments run via GitHub Actions on a **self-hosted runner** in the Production environment.

- **`deploy.yml`**: Deploys the full stack (Caddy + Homepage + media services). Triggers on push to `main` touching `infra/**`, or manual dispatch. The `.env` on the server holds only the 8 non-secret variables; secrets are passed only to the Homepage templating step.
- **`release-the-elephant.yml`**: Deploys PostgreSQL. Manual dispatch only.

There are no local build or deploy commands — everything runs through GitHub Actions workflows.

## Host

Ubuntu Server 26.04 LTS. Docker Engine + compose plugin from Docker's apt repo (not the snap — its confinement breaks bind mounts outside `$HOME`). The self-hosted runner runs as a systemd service under a user in the `docker` group and needs `gettext-base` (`envsubst`). `${MEDIA_ROOT}/data` must be a single filesystem for hardlinks.

## Key Conventions

- Configuration templates live under `infra/` and use the `.template` extension
- All container names and subdomains are hardcoded (no codename variables)
- Access control is enforced at the Caddy layer with graceful error handling for 502/503/504
- GitHub variables (8): `SERVER_NAME`, `SERVER_BASE_PATH`, `DOCKER_NETWORK`, `MEDIA_ROOT`, `TZ`, `PUID`, `PGID`, `VOIDROUTE_VPN_SUBNET`
