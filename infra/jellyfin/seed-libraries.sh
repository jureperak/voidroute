#!/usr/bin/env bash
# Creates the Movies and Shows libraries in Jellyfin through its API, with
# Croatian metadata and real-time monitoring. Libraries that already exist are
# skipped, so re-running is safe.
#
# Env: JELLYFIN_API_KEY
set -euo pipefail

: "${JELLYFIN_API_KEY:?JELLYFIN_API_KEY is not set}"

# get <path>
get() {
  docker exec -e APIKEY="$JELLYFIN_API_KEY" jellyfin \
    sh -c 'curl -sf -H "Authorization: MediaBrowser Token=\"$APIKEY\"" "http://localhost:8096$0"' "$1"
}

# add_library <name> <collection-type> <path>
add_library() {
  local name="$1" collection="$2" path="$3" existing body
  existing=$(get /Library/VirtualFolders \
    | python3 -c "import json,sys; print('\n'.join(v['Name'] for v in json.load(sys.stdin)))")
  if printf '%s\n' "$existing" | grep -qxF "$name"; then
    echo "jellyfin: library '$name' already exists"
    return 0
  fi

  body=$(python3 -c 'import json; print(json.dumps({"LibraryOptions": {
    "PreferredMetadataLanguage": "hr",
    "MetadataCountryCode": "HR",
    "EnableRealtimeMonitor": True}}))')

  printf '%s' "$body" | docker exec -i -e APIKEY="$JELLYFIN_API_KEY" jellyfin \
    sh -c 'curl -sf -X POST -H "Authorization: MediaBrowser Token=\"$APIKEY\"" -H "Content-Type: application/json" -d @- "http://localhost:8096/Library/VirtualFolders?name=$0&collectionType=$1&paths=$2&refreshLibrary=false"' \
    "$name" "$collection" "$path" >/dev/null
  echo "jellyfin: created library '$name'"
}

add_library Movies movies /media/movies
add_library Shows tvshows /media/series
