#!/usr/bin/env bash
# Push-to-talk with a USB headset plugged into the server.
#
#   Enter  -> start recording
#   Enter  -> stop, send to the assistant, and play the reply on this machine's audio output
#   q      -> quit
#
# The reply is not cast to the TV. /talk?local=true streams the reply as it is made: each
# speech clip (filler included) is played as soon as it arrives. Music requests still go to the TV.
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

# Reads the NDJSON stream on stdin and prints one "KIND value" line per event.
events() {
  python3 -u -c '
import json, sys
for line in sys.stdin:
    if not line.strip():
        continue
    ev = json.loads(line)
    if "error" in ev:
        print("ERROR", ev["error"], flush=True)
    elif "reason" in ev:
        print("NOTHEARD", ev["reason"], flush=True)
    elif "audio" in ev:
        print("SPEECH", ev["text"], flush=True)
        print("AUDIO", ev["audio"], flush=True)
    else:
        print("HEARD", ev["text"], flush=True)
'
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
  curl -fsSN --data-binary @"$rec" -H "Content-Type: audio/wav" "$VOICE_URL/talk?local=true" \
    | events \
    | while read -r kind value; do
        case "$kind" in
          HEARD)    echo "Čuo sam: $value" ;;
          NOTHEARD) echo "Nisam čuo: $value" ;;
          SPEECH)   echo "Odgovor: $value" ;;
          AUDIO)
            clip="$WORK/$(basename "$value")"
            curl -fsS -o "$clip" "$value" </dev/null
            aplay -q ${OUT_DEVICE:+-D "$OUT_DEVICE"} "$clip" </dev/null ;;
          ERROR)    echo "Greška na serveru: $value" ;;
        esac
      done || echo "Zahtjev nije uspio. Provjeri VOICE_URL i logove voice servisa."
done
