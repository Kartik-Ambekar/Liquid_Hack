#!/usr/bin/env python3
"""Smoke-test staged ZETIC LFM3 packages on the board, one capped request per input type.

Runs on the BOARD from ~/zetic-demo, next to run.py. Local files only.
Usage: python3 test_models.py [model-name ...]   (default: every staged model)
Full results append to zetic-results.jsonl; one compact line per request is printed.
"""

import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from run import run  # noqa: E402  (the repo's examples/zetic-lfm/run.py)

SDK = HERE / "sdk"
IMAGE = HERE / "samples/image_count/count.ppm"
AUDIO = HERE / "samples/asr/jfk.wav"
TEXT_PROMPT = "What is the capital of France? Answer in one short sentence."
CASES = {
    "lfm3-1.7b": ["text"],
    "lfm3-vl-2b": ["text", "image"],
    "lfm3-audio-2b": ["text", "audio"],
    "lfm3-omni-2b": ["text", "image", "audio"],
}


def one(name, kind):
    model = HERE / "models" / name
    if kind == "text":
        result = run(SDK, model, TEXT_PROMPT, max_tokens=64)
    elif kind == "image":
        result = run(SDK, model, "How many black circles are in the image?", image=IMAGE, max_tokens=64)
    else:
        result = run(SDK, model, "Transcribe the audio.", audio=AUDIO, max_tokens=128)
    result["test"] = {"package": name, "input": kind}
    with (HERE / "zetic-results.jsonl").open("a") as log:
        log.write(json.dumps(result) + "\n")
        log.flush()
    t = result["timings"]
    print(f"{'PASS' if result['ok'] else 'FAIL'} {name} {kind}"
          f" | load {t.get('model_load_ms')} ms ttft {t.get('runtime_ttft_ms')} ms"
          f" {t.get('runtime_decode_tok_s')} tok/s wall {t.get('wall_s', 0):.1f} s"
          f" | tokens {result['completion_tokens']} finish {result['finish_reason']}"
          f" | npu {'yes' if result['device_evidence'] else 'NO EVIDENCE'}", flush=True)
    print(f"     text: {result['text'][:150]!r}", flush=True)
    for error in result["errors"]:
        print(f"     error: {error}", flush=True)
    if not result["ok"] and result.get("stderr"):
        print("     stderr tail: " + " / ".join(result["stderr"].strip().splitlines()[-3:])[:300], flush=True)
    return result["ok"]


def main():
    names = sys.argv[1:] or list(CASES)
    passed = total = 0
    for name in names:
        if name not in CASES:
            print(f"SKIP {name}: unknown package")
            continue
        if not (HERE / "models" / name / "v73/manifest.json").is_file():
            print(f"SKIP {name}: not staged")
            continue
        for kind in CASES[name]:
            total += 1
            passed += one(name, kind)
    print(f"SUMMARY {passed}/{total} passed")
    return 0 if total and passed == total else 2


if __name__ == "__main__":
    raise SystemExit(main())
