#!/bin/bash
# Speak to Sister from the LAPTOP microphone for a fixed number of seconds.
# Sister runs on the board; the only link is the serial console.
# Usage: tools/talk.sh [seconds]     (default 4)
#
# If the push-to-talk console (tools/sister_console.py) is running, this asks it to record;
# holding SPACE in that console does the same thing without this script.
# Otherwise it records with the small recorder here and sends through a `screen` session.
set -euo pipefail
SECS="${1:-4}"
HERE="$(cd "$(dirname "$0")" && pwd)"
FIFO="$HERE/../.sister_console/inject"

if pgrep -f sister_console.py >/dev/null && [ -p "$FIFO" ]; then
  echo "Speak now ($SECS seconds)..."
  printf 'PTT %s' "$SECS" > "$FIFO"
  sleep "$SECS"
  echo "Sent through the push-to-talk console. Sister is transcribing on the board."
  exit 0
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
S="$( (screen -ls 2>/dev/null || true) | awk '/Attached|Detached/{print $1; exit}')"   # screen -ls exits 1 even when it lists sessions
[ -n "$S" ] || { echo "nothing is holding the board console; start tools/sister_console.py --start"; exit 1; }
REC="$HERE/.rec"
[ -x "$REC" ] || swiftc -O "$HERE/rec.swift" -o "$REC"   # first run only
echo "Speak now ($SECS seconds)..."
"$REC" "$TMP/in.wav" "$SECS"
python3 -c 'import sys, wave
w = wave.open(sys.argv[1]); assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (12000, 1, 2), w.getparams()
open(sys.argv[2], "wb").write(w.readframes(w.getnframes()))' "$TMP/in.wav" "$TMP/in.raw"
echo "Sending to the board..."
base64 -b 76 -i "$TMP/in.raw" -o "$TMP/in.b64"
SUM="$(shasum -a 256 "$TMP/in.raw" | cut -c1-64)"
screen -S "$S" -X stuff $'\025u\n'
sleep 1
screen -S "$S" -X readbuf "$TMP/in.b64"
screen -S "$S" -X paste .
sleep "$(( $(wc -c < "$TMP/in.b64") / 10000 + 3 ))"
screen -S "$S" -X stuff "END $SUM"$'\n'
echo "Sent. Sister is transcribing on the board."
