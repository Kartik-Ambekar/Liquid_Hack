#!/usr/bin/env bash
# Stage the ZETIC Ixian SDK 0.2.1, the repo's run.py wrapper, two fixtures and
# the four LFM3 IQ9 packages directly on the board, into ~/zetic-demo.
# Runs on the BOARD during approved online setup. Never run at app start.
# Usage: stage_zetic.sh all | sdk | model <name> <repo> <rev> | status
set -euo pipefail
D="$HOME/zetic-demo"
mkdir -p "$D/logs"
cd "$D"

dl() {
  local rc=0
  curl -fsSL --retry 5 --retry-delay 2 --connect-timeout 10 -C - -o "$2" "$1" || rc=$?
  # 22 on a rerun means the server refused to resume a complete file; checksums decide.
  if [ "$rc" -ne 0 ] && ! { [ "$rc" -eq 22 ] && [ -s "$2" ]; }; then
    echo "DOWNLOAD_FAIL rc=$rc $1"
    return 1
  fi
}

sdk() {
  local A=ixian-hexagon-0.2.1-linux-arm64-qcom-iq9.tar.gz
  local R=https://github.com/zetic-ai/IxianHexagon/releases/download/0.2.1
  local B=https://raw.githubusercontent.com/zetic-ai/LFM3-zetic-apps/35acef15824f4df435c36faf6439b2204a89c029
  local W=https://raw.githubusercontent.com/heath0xFF/cleared-for-takeoff-hackathon/b5715e4a0f10fda17efd2977c27989088d92ccd5
  dl "$R/$A" "$A"
  echo "afb426755bb793efd929fc1a8e37fb7a5bd2ff3133576d5f3e22de8bb7fe8b0b  $A" | sha256sum -c -
  if tar -tzf "$A" | grep -E '^/|(^|/)\.\.(/|$)'; then echo "SDK_FAIL unsafe path in archive"; exit 1; fi
  if tar -tvzf "$A" | grep -E '^[lh]'; then echo "SDK_FAIL archive contains links; inspect before extracting"; exit 1; fi
  mkdir sdk
  tar -xzf "$A" --strip-components=1 -C sdk
  local f
  for f in samples/image_count/count.ppm samples/asr/jfk.wav; do
    mkdir -p "$(dirname "$f")"
    dl "$B/$f" "$f"
  done
  dl "$W/examples/zetic-lfm/run.py" run.py
  echo "c429a13e0302654b0d2934e7fdf00f338b204c4479c23d3d02050f22f40300d4  run.py" | sha256sum -c -
  echo "SDK_OK"
}

model() {
  local n="$1" repo="$2" rev="$3"
  local m="models/$n"
  mkdir -p "$m"
  python3 - "$repo" "$rev" > "logs/$n.files" <<'PY'
import json, sys, urllib.request
repo, rev = sys.argv[1:3]
url = f"https://huggingface.co/api/models/{repo}/tree/{rev}?recursive=1"
for e in json.load(urllib.request.urlopen(url, timeout=30)):
    p = e["path"]
    if e["type"] != "file" or p.startswith("/") or ".." in p.split("/"):
        continue
    if p.startswith("v73/") or p in ("LICENSE", "README.md"):
        print(p)
PY
  local p
  while IFS= read -r p; do
    mkdir -p "$m/$(dirname "$p")"
    dl "https://huggingface.co/$repo/resolve/$rev/$p" "$m/$p"
  done < "logs/$n.files"
  (cd "$m/v73" && sha256sum -c --quiet SHA256SUMS)
  echo "MODEL_OK $n $(du -sh "$m" | cut -f1)"
}

models_list() {
  cat <<'L'
lfm3-omni-2b ZETIC-ai/LFM3-Omni-2B-IQ9 01d43f16d72df24a2f4239914a3768abe3d4ef1e
lfm3-1.7b ZETIC-ai/LFM3-1.7B-IQ9 585c80f796fa599d8c6aeb7e7948ae9ddeeca0dd
lfm3-vl-2b ZETIC-ai/LFM3-VL-2B-IQ9 4b97823becd3c17a050aef419924af48075eb199
lfm3-audio-2b ZETIC-ai/LFM3-Audio-2B-IQ9 5b4570b9de05bf511826b128d729b38ca29a5b79
L
}

case "${1:-}" in
  sdk) sdk ;;
  model) model "$2" "$3" "$4" ;;
  all)
    nohup "$0" sdk > logs/sdk.log 2>&1 &
    while read -r n repo rev; do
      nohup "$0" model "$n" "$repo" "$rev" > "logs/$n.log" 2>&1 &
    done < <(models_list)
    echo "STARTED sdk and 4 models; logs in $D/logs"
    ;;
  status)
    echo "sdk: $(tail -n 1 logs/sdk.log 2>/dev/null || echo none)"
    while read -r n _; do
      echo "$n: $(du -sh "models/$n" 2>/dev/null | cut -f1) $(tail -n 1 "logs/$n.log" 2>/dev/null)"
    done < <(models_list)
    echo "running: $(pgrep -fc 'stage_zetic.sh (sdk|model)' || true)"
    ;;
  *) echo "usage: $0 all | sdk | model <name> <repo> <rev> | status"; exit 2 ;;
esac
