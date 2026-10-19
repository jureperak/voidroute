#!/usr/bin/env bash
# Sets media management options in Sonarr and Radarr through their API:
# hardlinks instead of copies, renaming on import, and no empty folders.
# Only settings the app already has are changed; anything unknown is reported
# and left alone. Re-running is safe.
#
# Env: SONARR_API_KEY, RADARR_API_KEY
set -euo pipefail

: "${SONARR_API_KEY:?SONARR_API_KEY is not set}"
: "${RADARR_API_KEY:?RADARR_API_KEY is not set}"

# apply <container> <port> <key> <rename-field>
apply() {
  local container="$1" port="$2" key="$3" rename="$4" body
  body=$(docker exec -e APIKEY="$key" "$container" \
    sh -c 'curl -sf -H "X-Api-Key: $APIKEY" "http://localhost:$0/api/v3/config/mediamanagement"' "$port" \
    | python3 -c '
import json, sys
rename = sys.argv[1]
cfg = json.load(sys.stdin)
want = {
    "useHardlinks": True,
    "deleteEmptyFolders": True,
    "createEmptySeriesFolders": False,
    "createEmptyMovieFolders": False,
    rename: True,
}
for k in want:
    if k not in cfg:
        print(f"skipped unknown setting: {k}", file=sys.stderr)
changed = {k: v for k, v in want.items() if k in cfg and cfg[k] != v}
if changed:
    cfg.update(changed)
    print(json.dumps(cfg))
' "$rename")

  if [ -z "$body" ]; then
    echo "$container: media settings unchanged"
    return 0
  fi

  local id
  id=$(printf '%s' "$body" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
  printf '%s' "$body" | docker exec -i -e APIKEY="$key" "$container" \
    sh -c 'curl -sf -X PUT -H "X-Api-Key: $APIKEY" -H "Content-Type: application/json" -d @- "http://localhost:$0/api/v3/config/mediamanagement/$1"' \
    "$port" "$id" >/dev/null
  echo "$container: media settings updated"
}

apply sonarr 8989 "$SONARR_API_KEY" renameEpisodes
apply radarr 7878 "$RADARR_API_KEY" renameMovies
