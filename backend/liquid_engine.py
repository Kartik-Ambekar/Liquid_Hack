"""
liquid_engine.py - Liquid AI models on the Dragonwing IQ-9075, through the ZETIC Ixian CLI.

Every method here makes a real, capped request to a model staged on the board:
  - Speech to text:      LFM3-Omni-2B  (one WAV, up to 30 s, English)
  - Scan description:    LFM3-Omni-2B  (one 512x512 RGB image)
  - Plain explanation:   LFM3-1.7B     (text)

Nothing is simulated. If the runtime or a model is missing, or the answer fails
validation, the result has ok=False and an error list, and the caller falls back
to typed input or to the rule text. All timings come from the runtime's own log.

Layout expected on the board (override with SISTER_ZETIC_DIR):
  ~/zetic-demo/run.py            repo wrapper around zetic_lfm3_cli
  ~/zetic-demo/sdk/              Ixian Hexagon SDK 0.2.1
  ~/zetic-demo/models/<package>/v73/
"""

import importlib.util
import io
import os
import re
import time
import uuid
import wave
from pathlib import Path
from typing import Any, Dict, Optional

ZETIC_DIR = Path(os.environ.get("SISTER_ZETIC_DIR", "~/zetic-demo")).expanduser()
try:
    if ZETIC_DIR.exists():
        WORK_DIR = ZETIC_DIR / "work"
    else:
        WORK_DIR = Path(os.environ.get("SISTER_WORK_DIR", Path.cwd() / "work"))
except Exception:
    WORK_DIR = Path.cwd() / "work"
_run = None


def _wrapper():
    """Load the board's run.py once. Raises if the runtime is not staged."""
    global _run
    if _run is None:
        spec = importlib.util.spec_from_file_location("zetic_run", ZETIC_DIR / "run.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _run = module.run
    return _run


class LiquidAIEngine:
    AUDIO_PACKAGE = os.environ.get("SISTER_AUDIO_PKG", "lfm3-omni-2b")
    VISION_PACKAGE = os.environ.get("SISTER_VISION_PKG", "lfm3-omni-2b")
    TEXT_PACKAGE = os.environ.get("SISTER_TEXT_PKG", "lfm3-1.7b")

    @classmethod
    def call(cls, package: str, prompt: str, *, image: Optional[str] = None,
             audio: Optional[str] = None, max_tokens: int = 128, attempts: int = 2) -> Dict[str, Any]:
        """One capped request, validated by the wrapper, with a single retry."""
        started = time.perf_counter()
        out: Dict[str, Any] = {"ok": False, "text": "", "package": package, "errors": [], "attempts": 0}
        try:
            run = _wrapper()
        except Exception as exc:  # runtime not staged, or not on the board
            out["errors"].append(f"runtime unavailable: {type(exc).__name__}: {exc}")
            out["latency_ms"] = round((time.perf_counter() - started) * 1000, 1)
            return out
        result: Dict[str, Any] = {}
        for attempt in range(1, min(2, max(1, attempts)) + 1):
            out["attempts"] = attempt
            try:
                result = run(ZETIC_DIR / "sdk", ZETIC_DIR / "models" / package, prompt,
                             image=image, audio=audio, max_tokens=max_tokens)
            except Exception as exc:
                result = {"ok": False, "errors": [f"runtime error: {type(exc).__name__}: {exc}"]}
            if result.get("ok"):
                break
        timings = result.get("timings", {})
        out.update(
            ok=bool(result.get("ok")),
            text=result.get("text", ""),
            errors=list(result.get("errors", [])),
            model=(result.get("model") or {}).get("repo_id") if isinstance(result.get("model"), dict) else result.get("model"),
            precision=result.get("precision"),
            completion_tokens=result.get("completion_tokens"),
            finish_reason=result.get("finish_reason"),
            npu_evidence=bool(result.get("device_evidence")),
            load_ms=timings.get("model_load_ms"),
            ttft_ms=timings.get("runtime_ttft_ms"),
            tokens_per_sec=timings.get("runtime_decode_tok_s"),
            latency_ms=round((time.perf_counter() - started) * 1000, 1),
        )
        return out

    @classmethod
    def transcribe_audio_wav(cls, wav_bytes: bytes) -> Dict[str, Any]:
        """Transcribe one spoken answer on the board. WAV only, up to 30 seconds."""
        base = {"transcript": "", "ok": False, "errors": [], "duration_sec": None}
        try:
            with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
                base["duration_sec"] = round(wf.getnframes() / float(wf.getframerate()), 2)
        except Exception as exc:
            base["errors"].append(f"not a readable WAV file: {exc}")
            return base
        if base["duration_sec"] > 30:
            base["errors"].append("recording is longer than 30 seconds")
            return base
        try:
            _wrapper()
            WORK_DIR.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            base["errors"].append(f"audio runtime unavailable: {type(exc).__name__}")
            return base
        path = WORK_DIR / f"answer-{uuid.uuid4().hex}.wav"
        path.write_bytes(wav_bytes)
        try:
            result = cls.call(cls.AUDIO_PACKAGE, "Transcribe the audio.", audio=str(path), max_tokens=128)
        finally:
            path.unlink(missing_ok=True)
        # The model sometimes repeats the instruction after the transcript.
        # It can also repeat the wrapper's request tag; neither is something the patient said.
        text = re.sub(r"\s*\[request:[0-9a-f]+\]\s*", " ", result.get("text", ""))
        text = re.sub(r"\s*Transcribe the audio\.?\s*$", "", text, flags=re.I).strip()
        # A failed transcription is reported as a failure. No transcript is ever invented and no
        # timing is filled in: the caller asks the patient to say it again or type the answer.
        result.update(base | {"transcript": text, "ok": result["ok"] and bool(text),
                              "errors": result["errors"], "mode": "ZETIC Ixian CLI on the board"})
        return result

    # Plain words the model uses, mapped in code to the terms the triage rules look for.
    SCAN_FLAGS = (
        ("fracture", r"fractur|\bbreak|broken|\bcrack|disrupt"),
        ("opacity", r"opacit|cloudy|hazy|consolidat|white patch"),
        ("lesion", r"lesion|\bmass\b|bright[^.]{0,40}\bspot|abnormal signal"),
    )

    @classmethod
    def describe_scan(cls, image_path: str) -> Dict[str, Any]:
        """Describe one 512x512 RGB scan as observations for a clinician to confirm.

        The prompt does not suggest findings. Flags are derived from the model's own
        words by the patterns above, so the rules, not the model, decide urgency.
        """
        prompt = ("This is a medical scan. In two short plain sentences, say which body part it shows "
                  "and describe anything that looks unusual. If nothing looks unusual, say so. "
                  "Do not give a diagnosis.")
        result = cls.call(cls.VISION_PACKAGE, prompt, image=str(image_path), max_tokens=120)
        result["flags"] = [name for name, pattern in cls.SCAN_FLAGS if re.search(pattern, result["text"], re.I)]
        return result

    @classmethod
    def generate_clinical_explanation(cls, prompt: str, system_prompt: str = "") -> Dict[str, Any]:
        """Free-text generation with the text model."""
        return cls.call(cls.TEXT_PACKAGE, (system_prompt + "\n\n" + prompt).strip(), max_tokens=160)

    @classmethod
    def explain_decision(cls, decision: Dict[str, Any], session: Dict[str, Any]) -> Dict[str, Any]:
        """The rule has already decided. The model only rewords it for the patient."""
        prompt = (
            "You are Sister, a kind nurse speaking to a patient with no medical training. "
            "A safety rule has already decided how urgently they need care. Do not change that decision, "
            "do not name any disease, and do not give a diagnosis. In two or three short, simple sentences, "
            "tell the patient what to do and why.\n"
            f"Patient said: {'; '.join(session.get('symptoms', []))}. "
            f"For how long: {session.get('duration', '')}. How bad: {session.get('severity', '')}.\n"
            f"Decision: {decision.get('urgency_label')}.\n"
            f"Reason: {decision.get('summary_reason')}\n"
            f"What to do: {decision.get('recommended_action')}"
        )
        return cls.call(cls.TEXT_PACKAGE, prompt, max_tokens=160)

    SPEECH_PACKAGE = os.environ.get("SISTER_SPEECH_PKG", "lfm3-audio-2b")

    @classmethod
    def speak_to_wav(cls, text: str, out_path) -> Dict[str, Any]:
        """Text to speech on the board with LFM3-Audio-2B. Writes a WAV file; plays nothing."""
        import subprocess
        started = time.perf_counter()
        sdk = ZETIC_DIR / "sdk"
        out = {"ok": False, "errors": [], "package": cls.SPEECH_PACKAGE, "path": str(out_path)}
        command = [str(sdk / "bin/zetic_lfm3_cli"), "chat", "--model", str(ZETIC_DIR / "models" / cls.SPEECH_PACKAGE),
                   "--target", "v73", "--lib-dir", str(sdk / "lib"), "--max-tokens", "700", "--tts",
                   "--out", str(out_path), "--system", "Perform TTS in American English using a female voice.",
                   text.strip()]
        try:
            env = dict(os.environ, LD_LIBRARY_PATH=str(sdk / "lib"))
            done = subprocess.run(command, cwd=sdk, env=env, capture_output=True, text=True, timeout=120)
            log = done.stdout + done.stderr
            seconds = re.search(r"([\d.]+) s of audio", log)
            first = re.search(r"first audio ([\d.]+) ms", log)
            out.update(audio_seconds=float(seconds.group(1)) if seconds else None,
                       first_audio_ms=float(first.group(1)) if first else None)
            if done.returncode or not seconds or not Path(out_path).is_file():
                out["errors"].append(f"speech generation failed (exit {done.returncode})")
        except Exception as exc:
            out["errors"].append(f"{type(exc).__name__}: {exc}")
        out["ok"] = not out["errors"]
        out["latency_ms"] = round((time.perf_counter() - started) * 1000, 1)
        return out

    @classmethod
    def runtime_status(cls) -> Dict[str, Any]:
        """What is actually staged on this machine. No inference."""
        packages = {}
        for role, package in (("audio", cls.AUDIO_PACKAGE), ("vision", cls.VISION_PACKAGE), ("text", cls.TEXT_PACKAGE)):
            packages[role] = {"package": package,
                              "staged": (ZETIC_DIR / "models" / package / "v73" / "manifest.json").is_file()}
        return {"zetic_dir": str(ZETIC_DIR),
                "sdk_staged": (ZETIC_DIR / "sdk" / "bin" / "zetic_lfm3_cli").is_file(),
                "wrapper_staged": (ZETIC_DIR / "run.py").is_file(),
                "packages": packages}

    @classmethod
    def check_geniex_available(cls) -> bool:
        """Kept for callers of the old interface. Sister does not use GenieX."""
        return False
