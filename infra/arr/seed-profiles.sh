#!/usr/bin/env bash
# Creates the Sonarr and Radarr quality profiles stored in infra/arr/profiles,
# through each app's API. A profile is created only if no profile with the same
# name exists, so re-running is safe.
#
# Env: SONARR_API_KEY, RADARR_API_KEY
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"

seed() {
  local container="$1" port="$2" key="$3" file="$4" name existing
  name=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['name'])" "$file")

  existing=$(docker exec -e APIKEY="$key" "$container" \
    sh -c 'curl -sf -H "X-Api-Key: $APIKEY" http://localhost:'"$port"'/api/v3/qualityprofile' \
    | python3 -c "import json,sys; print('\n'.join(p['name'] for p in json.load(sys.stdin)))")

  if printf '%s\n' "$existing" | grep -qxF "$name"; then
    echo "$container: profile '$name' already exists"
    return 0
  fi

  python3 -c "import json,sys; d=json.load(open(sys.argv[1])); d['id']=0; print(json.dumps(d))" "$file" \
    | docker exec -i -e APIKEY="$key" "$container" \
      sh -c 'curl -sf -H "X-Api-Key: $APIKEY" -H "Content-Type: application/json" -X POST http://localhost:'"$port"'/api/v3/qualityprofile -d @-' \
    >/dev/null
  echo "$container: created profile '$name'"
}

seed sonarr 8989 "${SONARR_API_KEY:?SONARR_API_KEY is not set}" "$HERE/profiles/sonarr-my-series-profile.json"
seed radarr 7878 "${RADARR_API_KEY:?RADARR_API_KEY is not set}" "$HERE/profiles/radarr-my-movies-profile.json"
