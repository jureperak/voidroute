#!/usr/bin/env bash
# Adds qBittorrent as the download client, and the media root folder, to
# Sonarr and Radarr through their APIs. Anything already present is skipped,
# so re-running is safe.
#
# Env: SONARR_API_KEY, RADARR_API_KEY, QBITTORRENT_USERNAME, QBITTORRENT_PASSWORD
set -euo pipefail

: "${QBITTORRENT_USERNAME:?QBITTORRENT_USERNAME is not set}"
: "${QBITTORRENT_PASSWORD:?QBITTORRENT_PASSWORD is not set}"
: "${SONARR_API_KEY:?SONARR_API_KEY is not set}"
: "${RADARR_API_KEY:?RADARR_API_KEY is not set}"

# get <container> <port> <key> <path>
get() {
  docker exec -e APIKEY="$3" "$1" \
    sh -c 'curl -sf -H "X-Api-Key: $APIKEY" "http://localhost:$0$1"' "$2" "$4"
}

# post <container> <port> <key> <path>   (JSON body on stdin)
post() {
  docker exec -i -e APIKEY="$3" "$1" \
    sh -c 'curl -sf -H "X-Api-Key: $APIKEY" -H "Content-Type: application/json" -X POST "http://localhost:$0$1" -d @-' \
    "$2" "$4" >/dev/null
}

# add_qbittorrent <container> <port> <key> <category-field> <category>
add_qbittorrent() {
  local container="$1" port="$2" key="$3" catfield="$4" category="$5" existing body
  existing=$(get "$container" "$port" "$key" /api/v3/downloadclient \
    | python3 -c "import json,sys; print(' '.join(c['implementation'] for c in json.load(sys.stdin)))")
  case " $existing " in
    *" QBittorrent "*) echo "$container: qBittorrent already added"; return 0 ;;
  esac

  body=$(get "$container" "$port" "$key" /api/v3/downloadclient/schema | python3 -c '
import json, os, sys
catfield, category = sys.argv[1], sys.argv[2]
values = {
    "host": "qbittorrent",
    "port": 8080,
    "useSsl": False,
    "username": os.environ["QBITTORRENT_USERNAME"],
    "password": os.environ["QBITTORRENT_PASSWORD"],
    catfield: category,
}
schema = next(x for x in json.load(sys.stdin) if x["implementation"] == "QBittorrent")
for field in schema["fields"]:
    if field["name"] in values:
        field["value"] = values[field["name"]]
schema.update(name="qBittorrent", enable=True, protocol="torrent", priority=1,
              removeCompletedDownloads=True, removeFailedDownloads=True)
print(json.dumps(schema))
' "$catfield" "$category")

  printf '%s' "$body" | post "$container" "$port" "$key" /api/v3/downloadclient
  echo "$container: added qBittorrent (category $category)"
}

# add_root_folder <container> <port> <key> <path>
add_root_folder() {
  local container="$1" port="$2" key="$3" path="$4" existing
  existing=$(get "$container" "$port" "$key" /api/v3/rootfolder \
    | python3 -c "import json,sys; print(' '.join(r['path'] for r in json.load(sys.stdin)))")
  case " $existing " in
    *" $path "*) echo "$container: root folder $path already exists"; return 0 ;;
  esac

  printf '{"path":"%s"}' "$path" | post "$container" "$port" "$key" /api/v3/rootfolder
  echo "$container: added root folder $path"
}

add_qbittorrent sonarr 8989 "$SONARR_API_KEY" tvCategory tv-sonarr
add_root_folder sonarr 8989 "$SONARR_API_KEY" /data/media/series
add_qbittorrent radarr 7878 "$RADARR_API_KEY" movieCategory radarr
add_root_folder radarr 7878 "$RADARR_API_KEY" /data/media/movies
