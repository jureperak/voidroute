#!/usr/bin/env bash
# Sets media options in Sonarr and Radarr through their API:
#   - media management: hardlinks instead of copies, no empty folders
#   - naming: rename on import
# Only settings the app already has are changed; anything unknown is reported
# and left alone. Re-running is safe.
#
# Env: SONARR_API_KEY, RADARR_API_KEY
set -euo pipefail

: "${SONARR_API_KEY:?SONARR_API_KEY is not set}"
: "${RADARR_API_KEY:?RADARR_API_KEY is not set}"

# apply <container> <port> <key> <endpoint> <desired-json>
# endpoint is e.g. "config/mediamanagement"; desired-json is a JSON object of
# the settings to enforce. Settings the app does not have are skipped.
apply() {
  local container="$1" port="$2" key="$3" endpoint="$4" desired="$5" body id
  body=$(docker exec -e APIKEY="$key" "$container" \
    sh -c 'curl -sf -H "X-Api-Key: $APIKEY" "http://localhost:$0/api/v3/$1"' "$port" "$endpoint" \
    | python3 -c '
import json, sys
want = json.loads(sys.argv[1])
cfg = json.load(sys.stdin)
for k in want:
    if k not in cfg:
        print(f"{sys.argv[2]}: skipped unknown setting {k}", file=sys.stderr)
changed = {k: v for k, v in want.items() if k in cfg and cfg[k] != v}
if changed:
    cfg.update(changed)
    print(json.dumps(cfg))
' "$desired" "$container")

  if [ -z "$body" ]; then
    echo "$container: $endpoint unchanged"
    return 0
  fi

  id=$(printf '%s' "$body" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
  printf '%s' "$body" | docker exec -i -e APIKEY="$key" "$container" \
    sh -c 'curl -sf -X PUT -H "X-Api-Key: $APIKEY" -H "Content-Type: application/json" -d @- "http://localhost:$0/api/v3/$1/$2"' \
    "$port" "$endpoint" "$id" >/dev/null
  echo "$container: $endpoint updated"
}

apply sonarr 8989 "$SONARR_API_KEY" config/mediamanagement \
  '{"copyUsingHardlinks": true, "deleteEmptyFolders": true, "createEmptySeriesFolders": false}'
apply sonarr 8989 "$SONARR_API_KEY" config/naming '{"renameEpisodes": true}'

apply radarr 7878 "$RADARR_API_KEY" config/mediamanagement \
  '{"copyUsingHardlinks": true, "deleteEmptyFolders": true, "createEmptyMovieFolders": false}'
apply radarr 7878 "$RADARR_API_KEY" config/naming '{"renameMovies": true}'
