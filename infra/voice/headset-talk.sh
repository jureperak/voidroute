#!/usr/bin/env bash
# Push-to-talk with a USB headset plugged into the server.
#
#   Enter  -> start recording
#   Enter  -> stop, send to the assistant, play the reply on this machine's audio output
#   q      -> quit
#
# The reply is not cast to the TV: /talk?local=true returns the clip URLs and this
# script plays them. Music requests still go to the TV.
#
# Setup on the server (once):
#   sudo apt install alsa-utils curl python3
#   arecord -l    # note the card of the headset, e.g. card 2 -> plughw:2,0
#   aplay -l      # note the output device, if it is not the default
#   chmod +x headset-talk.sh
#
# Run:
#   VOICE_URL=https://voice.<your-domain> AUDIO_DEVICE=plughw:2,0 ./headset-talk.sh
set -euo pipefail

: "${VOICE_URL:?set VOICE_URL, e.g. https://voice.example.com}"
AUDIO_DEVICE="${AUDIO_DEVICE:-plughw:2,0}"   # capture: headset mic, from `arecord -l`
OUT_DEVICE="${OUT_DEVICE:-}"                 # playback: empty = default output, or e.g. plughw:2,0
WORK="${WORK:-$HOME/.cache/voidroute-voice}"

for cmd in arecord aplay curl python3; do
  command -v "$cmd" >/dev/null || { echo "Missing: $cmd (see setup in this file)." >&2; exit 1; }
done
mkdir -p "$WORK"

json_field() {  # json_field <key>: read JSON on stdin, print one top-level value
  python3 -c 'import json,sys; v=json.load(sys.stdin).get(sys.argv[1], ""); print(v if isinstance(v,str) else "")' "$1"
}

while true; do
  read -r -p "Enter = snimi, q = izlaz: " key || exit 0
  [[ "$key" == "q" ]] && exit 0

  rec="$WORK/question.wav"
  arecord -q -D "$AUDIO_DEVICE" -f S16_LE -r 16000 -c 1 "$rec" &
  pid=$!
  echo "Snimam... Enter za kraj."
  read -r _ || true
  kill -INT "$pid" 2>/dev/null || true
  wait "$pid" 2>/dev/null || true

  echo "Šaljem..."
  if ! resp=$(curl -fsS --data-binary @"$rec" -H "Content-Type: audio/wav" \
                "$VOICE_URL/talk?local=true"); then
    echo "Zahtjev nije uspio. Provjeri VOICE_URL i logove voice servisa."
    continue
  fi

  text=$(printf '%s' "$resp" | json_field text)
  if [[ -z "$text" ]]; then
    echo "Nisam čuo: $(printf '%s' "$resp" | json_field reason)"
    continue
  fi
  echo "Čuo sam: $text"
  printf '%s' "$resp" | python3 -c 'import json,sys
for t in json.load(sys.stdin).get("speech", []): print("Odgovor:", t)'

  printf '%s' "$resp" | python3 -c 'import json,sys
for u in json.load(sys.stdin).get("audio", []): print(u)' |
  while read -r url; do
    clip="$WORK/$(basename "$url")"
    curl -fsS -o "$clip" "$url"
    aplay -q ${OUT_DEVICE:+-D "$OUT_DEVICE"} "$clip"
  done
done
