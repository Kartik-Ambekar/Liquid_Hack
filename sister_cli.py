#!/usr/bin/env python3
"""
sister_cli.py - Sister in a terminal, for the Wi-Fi-off demo over the board's serial console.

Same interview and the same deterministic triage rules as the web app
(backend/session_manager.py, backend/triage_rules.py). Standard library only.

At any question you can:
  type an answer            free text
  type a number             pick one of the listed choices
  v <file.wav>              answer by voice from a WAV file (transcribed on the board)
  r                         record 5 seconds from the board's microphone, then transcribe
  u                         receive a recording sent from the laptop microphone (tools/talk.sh does this)
At the scan question:
  s <number>                use a sample scan        s <file>   use your own 512x512 image

Usage: python3 sister_cli.py [--no-explain] [--speak]
  --speak   Sister says each question aloud through the board speaker (SISTER_SPEAKER, default plughw:0,0)
            at SISTER_VOLUME (default 0.5). Speech is generated on the board and cached in tts_cache/.
"""

import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import warnings
import wave
from pathlib import Path

warnings.simplefilter("ignore", DeprecationWarning)  # audioop, still present in the board's Python 3.12

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from backend.liquid_engine import LiquidAIEngine, WORK_DIR  # noqa: E402
from backend.session_manager import SessionManager, AUDIT_LOG_FILE  # noqa: E402
from backend.triage_rules import RULESET_STATUS  # noqa: E402

SAMPLES = sorted(p for p in (HERE / "samples").iterdir() if p.suffix.lower() in (".png", ".jpg"))
SCAN_TYPES = (("chest", "Chest X-ray", "X-RAY_CHEST"), ("bone", "Bone X-ray", "X-RAY_BONE"),
              ("brain", "Brain MRI", "MRI_BRAIN"), ("spine", "Spine MRI", "MRI_SPINE"))


SPEAK = "--speak" in sys.argv
SPEAKER = os.environ.get("SISTER_SPEAKER", "plughw:0,0")
VOLUME = float(os.environ.get("SISTER_VOLUME", "0.5"))


def say(text, spoken=None):
    print("\nSISTER: " + re.sub(r"\*\*", "", text), flush=True)
    if SPEAK:
        speak(spoken or text)


def speak(text):
    """Generate speech on the board (cached per sentence) and play it at SISTER_VOLUME."""
    import audioop  # in the board's Python 3.12
    clean = re.sub(r"\s+", " ", re.sub(r"\*\*|[^\x20-\x7e]", " ", text)).strip()
    cache = HERE / "tts_cache"
    cache.mkdir(exist_ok=True)
    path = cache / (hashlib.sha256(clean.encode()).hexdigest()[:16] + ".wav")
    if not path.is_file():
        result = LiquidAIEngine.speak_to_wav(clean, path)
        SessionManager._flush_log({"event": "SPEECH_OUT", "ok": result["ok"], "errors": result["errors"],
                                   "audio_seconds": result.get("audio_seconds"), "latency_ms": result.get("latency_ms")})
        if not result["ok"]:
            print(f"  (could not speak: {'; '.join(result['errors'])})")
            path.unlink(missing_ok=True)
            return
        print(f"  [spoken by LFM3-Audio-2B on the board: {result.get('audio_seconds')} s of speech, "
              f"first audio {result.get('first_audio_ms')} ms, generated in {result.get('latency_ms')} ms]", flush=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    quiet = WORK_DIR / "say.wav"
    with wave.open(str(path), "rb") as src, wave.open(str(quiet), "wb") as dst:
        dst.setparams(src.getparams())
        dst.writeframes(audioop.mul(src.readframes(src.getnframes()), src.getsampwidth(), VOLUME))
    subprocess.run(["aplay", "-q", "-D", SPEAKER, str(quiet)], capture_output=True)


def receive_upload():
    """Read base64 PCM (16-bit mono, 12 kHz) from the console until 'END <sha256>', then transcribe."""
    import audioop
    import termios
    fd, old = sys.stdin.fileno(), None
    try:
        old = termios.tcgetattr(fd)
        new = termios.tcgetattr(fd)
        new[3] &= ~termios.ECHO
        termios.tcsetattr(fd, termios.TCSANOW, new)
    except Exception:
        pass
    print("  receiving audio from the laptop microphone...", flush=True)
    chunks, expected = [], ""
    try:
        for line in sys.stdin:
            line = line.strip()
            if line.startswith("END"):
                expected = line[3:].strip()
                break
            chunks.append(line)
    finally:
        if old:
            termios.tcsetattr(fd, termios.TCSANOW, old)
    try:
        pcm = base64.b64decode("".join(chunks))
    except Exception:
        pcm = b""
    if not pcm or hashlib.sha256(pcm).hexdigest() != expected:
        print("  the recording was damaged on the way here. Please say it again, or type your answer.")
        return None
    pcm, _ = audioop.ratecv(pcm, 2, 1, 12000, 16000, None)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    path = WORK_DIR / "from_laptop.wav"
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(16000)
        out.writeframes(pcm)
    print(f"  received {len(pcm) / 32000:.1f} s of audio intact; transcribing on the board...", flush=True)
    return transcribe(path)


def metrics(result):
    return (f"[{result.get('model') or result.get('package')} on the board | load {result.get('load_ms')} ms, "
            f"first token {result.get('ttft_ms')} ms, {result.get('tokens_per_sec')} tok/s, "
            f"total {result.get('latency_ms')} ms | NPU evidence: {'yes' if result.get('npu_evidence') else 'no'}]")


def transcribe(path):
    result = LiquidAIEngine.transcribe_audio_wav(Path(path).expanduser().read_bytes())
    SessionManager._flush_log({"event": "TRANSCRIPTION", "file": str(path), "ok": result["ok"],
                               "transcript": result["transcript"], "errors": result["errors"],
                               "latency_ms": result.get("latency_ms"), "model": result.get("model")})
    if not result["ok"]:
        print(f"  could not transcribe ({'; '.join(result['errors'])}). Please type your answer.")
        return None
    print(f"  What Sister heard: \"{result['transcript']}\"\n  {metrics(result)}")
    return result["transcript"]


def record():
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    path = WORK_DIR / "mic.wav"
    print("  recording 5 seconds from the board microphone...", flush=True)
    done = subprocess.run(["arecord", "-q", "-d", "5", "-f", "S16_LE", "-r", "16000", "-c", "1", str(path)],
                          capture_output=True, text=True)
    if done.returncode:
        print(f"  recording failed: {done.stderr.strip()[:200]}")
        return None
    return transcribe(path)


def ingest_scan(session_id, arg):
    path = SAMPLES[int(arg) - 1] if arg.isdigit() and 0 < int(arg) <= len(SAMPLES) else Path(arg).expanduser()
    print(f"  looking at {path.name} with the vision model...", flush=True)
    result = LiquidAIEngine.describe_scan(str(path))
    if not result["ok"]:
        print(f"  could not read the scan ({'; '.join(result['errors'])}). Continuing without it.")
        SessionManager._flush_log({"event": "IMAGING_FAILED", "session_id": session_id, "file": path.name,
                                   "errors": result["errors"]})
        return SessionManager.process_turn(session_id, "no", "choice")
    scan = next((s for s in SCAN_TYPES if s[0] in path.name.lower() or s[0] in result["text"].lower()),
                (None, "medical scan", "UNKNOWN"))
    print(f"  {metrics(result)}")
    analysis = {"scan_type": scan[1], "detected_modality": scan[2], "modality": scan[2], "filename": path.name,
                "primary_observation": result["text"] + (f" (flagged for clinician review: {', '.join(result['flags'])})" if result["flags"] else ""),
                "flags": result["flags"], "urgency_flag": "", "source": "model observation, unconfirmed",
                "model": result.get("model"), "latency_ms": result.get("latency_ms")}
    return SessionManager.attach_imaging_analysis(session_id, analysis)


def main():
    explain = "--no-explain" not in sys.argv
    status = LiquidAIEngine.runtime_status()
    print("=" * 72)
    print(" SISTER  offline health triage  |  runs on this board, no network needed")
    print(" models staged: " + ", ".join(f"{role}={p['package']}{'' if p['staged'] else ' (MISSING)'}"
                                         for role, p in status["packages"].items()))
    print(" triage is decided by rules in code; the models listen, look and explain")
    print(f" rules: {RULESET_STATUS}")
    print("=" * 72)
    session = SessionManager.create_session()
    sid = session["session_id"]
    response = SessionManager.get_initial_prompt()
    while True:
        say(response.get("sister_message", ""), response.get("spoken_text"))
        if response.get("status") in ("completed", "error"):
            break
        choices = response.get("choices", [])
        for index, choice in enumerate(choices, 1):
            print(f"   {index}. " + re.sub(r"[^\x20-\x7e]+", "", choice["label"]).strip())  # serial console is ASCII
        if response.get("step") in ("GREETING_INGEST", "AWAITING_INGEST"):
            print("   scans: " + "  ".join(f"s {i}={p.stem}" for i, p in enumerate(SAMPLES, 1)))
        try:
            raw = input("YOU> ").strip()
        except EOFError:
            return 1
        if not raw:
            continue
        kind, answer = "text", raw
        if raw.lower().startswith("s ") and response.get("step") in ("GREETING_INGEST", "AWAITING_INGEST"):
            response = ingest_scan(sid, raw[2:].strip())
            continue
        if raw.lower().startswith("v "):
            kind, answer = "voice", transcribe(raw[2:].strip())
        elif raw.lower() == "r":
            kind, answer = "voice", record()
        elif raw.lower() == "u":
            kind, answer = "voice", receive_upload()
        elif raw.isdigit() and 0 < int(raw) <= len(choices):
            kind, answer = "choice", re.sub(r"^[^\w]+", "", choices[int(raw) - 1]["label"]).strip()
        if not answer:
            continue
        response = SessionManager.process_turn(sid, answer, kind)

    decision = SessionManager.get_session(sid).get("triage_decision") or {}
    print("\n" + "-" * 72)
    print(f" DECISION (by rule {decision.get('rule_fired')}): {decision.get('urgency_label')}")
    print("-" * 72)
    if explain and decision:
        print("  asking the text model to explain it in plain words...", flush=True)
        result = LiquidAIEngine.explain_decision(decision, SessionManager.get_session(sid))
        SessionManager._flush_log({"event": "MODEL_EXPLANATION", "session_id": sid, "ok": result["ok"],
                                   "text": result["text"], "errors": result["errors"],
                                   "latency_ms": result.get("latency_ms"), "model": result.get("model"),
                                   "rule_fired": decision.get("rule_fired")})
        if result["ok"]:
            say(result["text"])
            print(f"  {metrics(result)}")
        else:
            print(f"  explanation unavailable ({'; '.join(result['errors'])}); the rule's wording above stands.")
    note = SessionManager.get_session(sid).get("handover_note") or {}
    if note.get("raw_text"):
        path = HERE / f"handover-{sid}.txt"
        path.write_text(note["raw_text"])
        print(f"\n handover note for the clinic: {path}")
    print(f" audit log: {AUDIT_LOG_FILE}")
    print(" last log lines:")
    for entry in SessionManager.read_audit_log(limit=4):
        print("   " + json.dumps(entry)[:200])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
