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
| Seerr | Request/discovery UI (successor to Jellyseerr, image `ghcr.io/seerr-team/seerr`, pinned to `v3.5.0`) | jellyseerr.* |
| Flaresolverr | Cloudflare solver for Prowlarr | (internal only) |
| Portainer | Docker management UI | portainer.* |
| Docker socket proxy | Read-only Docker API for Homepage | (internal only) |
| AdGuard Home | DNS/ad blocking (external) | adguard.* |
| PostgreSQL | Database (separate workflow) | — |

## Architecture

**Caddy** handles TLS, subdomain routing, and IP-based access control (local network 192.168.8.0/24 + VPN subnet). DNS is split-brain: AdGuard Home rewrites `*.${SERVER_NAME}` to the server's LAN IP, and remote access is via VPN only. Caddy serves a single `*.${SERVER_NAME}` site. Its intended certificate is one wildcard from Let's Encrypt via DNS-01 against Porkbun, so ports 80/443 do not need to be reachable from the internet. Caddy is built from `infra/caddy/Dockerfile` (`caddy:2` + `caddy-dns/porkbun`); the Porkbun keys (`PORKBUN_API_KEY`, `PORKBUN_API_SECRET_KEY` secrets) are written by the deploy to `${SERVER_BASE_PATH}/caddy/caddy.env`. To add a service, add one `import service <subdomain> <upstream>` line to the Caddyfile. All services run on a shared `voidroute` Docker network, with only Caddy exposed on ports 80/443. PostgreSQL joins the same network and publishes 5432 on `127.0.0.1` only.

**Current state:** Caddy gets a real wildcard certificate via DNS-01 against Porkbun. Two settings make it work: `propagation_delay 120s` (Porkbun publishes new TXT records with a delay) and `propagation_timeout -1` (Caddy skips its own check, because its resolver caches stale "no record" answers for up to 30 minutes, and Let's Encrypt validates directly). The split-brain DNS needs per-service AdGuard rewrites (`homepage.*`, `jellyfin.*`, ...), not a wildcard, because a wildcard rewrite answers `_acme-challenge` TXT queries itself. Devices must use AdGuard for DNS to resolve these names; the public DNS records for `voidroute.dev` were removed.

A separate `homepage-mgmt` network (internal, `172.30.254.0/28`, dynamic IPs limited to `.8-.15`) connects Homepage, Caddy and `dockerproxy`. Caddy's admin API binds only to its static IP there (`172.30.254.2:2019`), and Homepage reaches Docker via `dockerproxy:2375` (containers read-only) instead of mounting `docker.sock`.

**Folder layout** follows TRaSH Guides conventions:
```
${MEDIA_ROOT}/
├── config/{jellyfin,qbittorrent,sonarr,radarr,prowlarr,bazarr,jellyseerr}/
└── data/
    ├── downloads/torrents/{movies,series,incomplete}/
    └── media/{movies,series}/
```

qBittorrent, Sonarr and Radarr mount `${MEDIA_ROOT}/data` as a single `/data` volume so imports use hardlinks and atomic moves. Do not split it into separate `/downloads` and `/media` mounts — hardlinks/renames fail across bind mounts and fall back to copying.

**Template system**: `.template` files use `${VAR_NAME}` placeholders, substituted at deploy time via `envsubst`. Sensitive values (API keys, passwords) come from GitHub Actions secrets; non-sensitive config from GitHub Actions variables.

## Automated configuration

The deploy also wires the apps together through their APIs. Each step is idempotent: it checks for an existing item and skips it, so re-running the deploy is safe. Scripts live in `infra/`, and are called from `deploy.yml` after `Deploy stack`.

| Step | Script | What it does |
|---|---|---|
| Seed arr API keys | inline in `deploy.yml` | Writes the Sonarr/Radarr/Prowlarr keys into each `config.xml`, and Bazarr's key into its `config.yaml` (`auth:` section). Restarts an app only if its key changed. |
| Link Prowlarr to Sonarr and Radarr | inline in `deploy.yml` | Registers both apps as Prowlarr applications via Prowlarr's API. |
| Link Seerr to Sonarr and Radarr | `infra/seerr/link-arr.js` | Uses Seerr's API to test each connection, then saves it with the matching profile and root folder. |
| Seed Sonarr and Radarr quality profiles | `infra/arr/seed-profiles.sh` | Creates `My series profile` and `My movies profile` from `infra/arr/profiles/*.json`. |
| Add qBittorrent and root folders | `infra/arr/seed-download-clients.sh` | Adds the qBittorrent download client (categories `tv-sonarr` / `radarr`) and the `/data/media` root folders. |
| Set media settings | `infra/arr/seed-media-settings.sh` | Sets `copyUsingHardlinks`, `deleteEmptyFolders` and renaming. Uses `config/mediamanagement` and `config/naming`. |
| Create Jellyfin libraries | `infra/jellyfin/seed-libraries.sh` | Creates the Movies and Shows libraries with Croatian metadata, if missing. |

Use the app's own field names: they're in each app's source (`MediaManagementConfigResource.cs`, `NamingConfigResource.cs`). Guessed names are silently skipped, not errors.

**Manual, on purpose:** Bazarr's language profile (its settings endpoint replaces the whole profile list, so scripting it can delete profiles), and Prowlarr's indexers (tracker credentials differ per tracker).

## Secrets and variables

GitHub **secrets**: `PORKBUN_API_KEY`, `PORKBUN_API_SECRET_KEY`, `JELLYFIN_API_KEY`, `SEERR_API_KEY`, `SONARR_API_KEY`, `RADARR_API_KEY`, `PROWLARR_API_KEY`, `BAZARR_API_KEY`, `QBITTORRENT_USERNAME`, `QBITTORRENT_PASSWORD`.

The arr keys can be any 32-character hex string, generated with `openssl rand -hex 16`. The deploy writes them into each app. `SEERR_API_KEY` and `JELLYFIN_API_KEY` are created inside those apps, after their first start.

## Backup

`infra/backup/backup.sh` backs up configuration only, not media: `${MEDIA_ROOT}/config`, Caddy's data folder, and Portainer's data folder. It uses restic, and it runs from a systemd timer installed once on the server by `infra/backup/install-timer.sh`. Settings are in `~/.config/voidroute-backup.env`, from `backup.env.example`. The restic password must be stored outside the server. **Not yet set up:** the planned destination is a NAS, since OneDrive was declined.

## Deployment

Deployments run via GitHub Actions on a **self-hosted runner** in the Production environment.

- **`deploy.yml`**: Deploys the full stack (Caddy + Homepage + media services). Triggers only when a merged PR changes files under `infra/**` into `main` (direct pushes to `main` do not deploy), or on manual dispatch from `main`. Changes to `.github/workflows/` alone do not trigger a deploy; run it manually with `gh workflow run deploy.yml --ref main`. The `.env` on the server holds only the 8 non-secret variables; secrets are passed only to the steps that need them.
- **`release-the-elephant.yml`**: Deploys PostgreSQL. Manual dispatch only.

There are no local build or deploy commands — everything runs through GitHub Actions workflows.

## Bootstrapping from zero

1. **Host:** Ubuntu Server 26.04 LTS, Docker Engine + compose plugin, `git`, and `gettext-base`. Install the self-hosted runner as a systemd service under your user (`sudo ./svc.sh install <user>`), in the `docker` group, with the default `self-hosted` label. Create the folders from the layout above, owned by your user (`id -u` / `id -g` should match `PUID` / `PGID`).
2. **Porkbun:** enable API access for `voidroute.dev` (Opt In All Domains), and create an API key with DNS permission only. Caddy's DNS-01 settings are in the `tls` block (see Current state). Remove the public `*` CNAME and apex ALIAS for `voidroute.dev`, and create the per-service AdGuard rewrites instead.
3. **GitHub:** set the 8 variables and the secrets above, except `JELLYFIN_API_KEY` and `SEERR_API_KEY`. Generate the arr keys with `openssl rand -hex 16`.
4. **First deploy:** run Deploy manually from `main`. Its early steps skip the apps that don't exist yet, and check the log for warnings.
5. **Apps' first start:** complete each app's first-run setup:
   - **qBittorrent:** the temporary password is in `docker logs qbittorrent`. Set the username and password to match the secrets, then re-run the deploy.
   - **Jellyfin:** create the admin account, create an API key under Dashboard → API Keys, and store it as `JELLYFIN_API_KEY`.
   - **Seerr:** sign in with Jellyfin (hostname `jellyfin`, port `8096`, SSL off). Skip the Sonarr and Radarr steps; the deploy adds them. Create an API key under Settings → General, and store it as `SEERR_API_KEY`.
   - **Prowlarr:** set authentication. Add indexers by hand.
   - **Bazarr:** create the language profile by hand (Croatian first, then Bosnian, Serbo-Croatian, English; cutoff Croatian), and add a subtitle provider.
6. **Second deploy:** re-run once the secrets are set. It links Seerr, adds Jellyfin libraries, and so on.
7. **Homepage:** the Jellyfin widget needs `version: 2` (Jellyfin 12+).

## Known gaps

- **Porkbun TXT publication:** new TXT records take time to appear, and records can disappear when a challenge fails. Support ticket open. The propagation settings above work around it.
- **Bazarr profile and Prowlarr indexers:** manual, see Automated configuration.
- **Backup:** not yet running. Waiting for the NAS.
- **Seerr:** pinned to `v3.5.0`. Check the release notes before each bump.

## Host

Ubuntu Server 26.04 LTS. Docker Engine + compose plugin from Docker's apt repo (not the snap — its confinement breaks bind mounts outside `$HOME`). The self-hosted runner runs as a systemd service under a user in the `docker` group and needs `gettext-base` (`envsubst`). `${MEDIA_ROOT}/data` must be a single filesystem for hardlinks.

## Key Conventions

- Configuration templates live under `infra/` and use the `.template` extension
- All container names and subdomains are hardcoded (no codename variables)
- Access control is enforced at the Caddy layer with graceful error handling for 502/503/504
- No service except Caddy publishes host ports; everything else is reached via the Docker network
- GitHub variables (8): `SERVER_NAME`, `SERVER_BASE_PATH`, `DOCKER_NETWORK`, `MEDIA_ROOT`, `TZ`, `PUID`, `PGID`, `VOIDROUTE_VPN_SUBNET`
