#!/usr/bin/env python3
"""
sister_console.py - laptop console for Sister with push-to-talk.

Runs on the LAPTOP. It owns the board's serial console, keeps the laptop microphone
open, and shows Sister exactly as the board prints her. All inference stays on the board.

  Hold SPACE   record from the laptop microphone
  Release      the recording is sent down the serial line and transcribed on the board
  Type         everything else goes to the board as usual (a quick tap of space is a space)
  Ctrl-]       quit this console (Sister keeps running on the board)

It also serves a status page at http://127.0.0.1:8765 (loopback only): whose turn it is,
the conversation, the rule decision and the board log, with hold-SPACE-to-talk in the browser.

Usage: tools/sister_console.py [--start] [--port /dev/cu.usbserial-XXXX] [--mic N]
  --start   if the board is at a shell prompt, start Sister in speaking mode
Close any `screen` session on the same port first; only one program can own it.

A terminal cannot see a key being released, so "release" is detected as the end of the
key's auto-repeat. Standard library only, plus ffmpeg for the microphone.
"""

import argparse
import base64
import glob
import hashlib
import os
import re
import select
import subprocess
import sys
import termios
import time
import tty
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dashboard import Dashboard  # noqa: E402

RATE = 12000                  # mu-law, mono: 12 kB per second of speech on a 115200 baud line
TAP_WINDOW = 0.70             # no auto-repeat within this long after a press: it was a typed space
RELEASE_GAP = 0.30            # auto-repeat stopped for this long: the key was released
PREROLL = int(RATE * 0.35)    # speech just before the key registered is kept
MIN_SPEECH = int(RATE * 0.5)
MAX_SPEECH = RATE * 28        # the board accepts up to 30 seconds
# Default: the SAMPLE history interview (sister_cli.py, backend/sample_interview.py).
# SISTER_SHORT=1 asks only the first half of the questionnaire, which is what fits a demo.
# SISTER_MAX_PROMPT_CHARS=0 turns the model-based extractor off: on the board (2026-11-13) its
# output failed validation on both attempts and cost about 20 s per answer before the fallback.
START_CMD = b"cd ~/sister && SISTER_SHORT=1 SISTER_MAX_PROMPT_CHARS=0 python3 -W ignore sister_cli.py --speak --no-explain\n"
# --classic: the earlier four-step voice demo.
CLASSIC_CMD = b"cd ~/sister && python3 -W ignore sister_voice_demo.py --speak\n"
STATE_DIR = Path(__file__).resolve().parent.parent / ".sister_console"
ANSI = re.compile(rb"\x1b\[[0-9;?]*[A-Za-z]")


def note(text):
    os.write(1, f"\r\n\x1b[2m  [laptop] {text}\x1b[0m\r\n".encode())


class Console:
    def __init__(self, port, mic, web_port=8765, classic=False):
        self.start_cmd = CLASSIC_CMD if classic else START_CMD
        self.dash = Dashboard(web_port)
        self.level, self.sending = 0.0, False
        self.serial = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        tty.setraw(self.serial)
        attrs = termios.tcgetattr(self.serial)
        attrs[2] |= termios.CLOCAL | termios.CREAD
        attrs[4] = attrs[5] = termios.B115200
        termios.tcsetattr(self.serial, termios.TCSANOW, attrs)
        self.mic = subprocess.Popen(
            ["ffmpeg", "-loglevel", "error", "-f", "avfoundation", "-i", f":{mic}", "-ar", str(RATE),
             "-ac", "1", "-flush_packets", "1", "-f", "mulaw", "-"],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
        os.set_blocking(self.mic.stdout.fileno(), False)
        STATE_DIR.mkdir(exist_ok=True)
        self.log = open(STATE_DIR / "board.log", "ab", buffering=0)
        self.fifo_path = STATE_DIR / "inject"
        if not self.fifo_path.exists():
            os.mkfifo(self.fifo_path)
        # Read-write so the pipe never reports end-of-file when a writer disconnects.
        self.fifo = os.open(self.fifo_path, os.O_RDWR | os.O_NONBLOCK)
        self.tail = b""               # recent board output, to tell when Sister is waiting
        self.preroll = bytearray()
        self.speech = bytearray()
        self.state = "idle"           # idle | pending | holding | timed
        self.pressed = self.last_repeat = self.timed_until = 0.0

    # --- board -----------------------------------------------------------------
    def write_serial(self, data):
        view = memoryview(data)
        while view:
            try:
                view = view[os.write(self.serial, view[:512]):]
            except BlockingIOError:
                select.select([], [self.serial], [], 0.2)

    def read_serial(self):
        try:
            data = os.read(self.serial, 4096)
        except BlockingIOError:
            return
        if data:
            os.write(1, data)
            self.log.write(data)
            self.dash.feed(data)
            self.tail = (self.tail + ANSI.sub(b"", data))[-400:]

    def waiting_for_answer(self):
        return self.tail.rstrip(b" ").endswith(b"YOU>")

    def confirming(self):
        """The SAMPLE interview asks the patient to confirm each transcript before it is used."""
        return self.tail.rstrip(b" ").endswith(b"[y/N]")

    # --- microphone ------------------------------------------------------------
    def read_mic(self):
        try:
            data = os.read(self.mic.stdout.fileno(), 8192)
        except BlockingIOError:
            return
        if not data:
            return
        self.level = max((b ^ 0xFF) & 0x7F for b in data[::16]) / 127   # rough loudness from mu-law, for the meter
        if self.state == "idle":
            self.preroll = (self.preroll + data)[-PREROLL:]
        else:
            self.speech += data

    def begin(self, state):
        self.speech = bytearray(self.preroll)
        self.state, self.pressed, self.last_repeat = state, time.monotonic(), time.monotonic()

    def cancel(self):
        self.state, self.speech = "idle", bytearray()

    def finish(self):
        time.sleep(0.12)              # let the last audio reach us
        self.read_mic()
        speech, self.state, self.speech = bytes(self.speech), "idle", bytearray()
        if len(speech) < MIN_SPEECH:
            note("too short to be speech; hold SPACE while you talk")
            self.dash.note("That was too short to be speech. Hold SPACE while you talk.")
            return
        if not self.waiting_for_answer():
            note("Sister is not waiting for an answer right now; nothing was sent")
            self.dash.note("Sister was not waiting for an answer, so nothing was sent.")
            return
        self.sending = True
        self.sync()
        try:
            self.send(speech)
        finally:
            self.sending = False

    def sync(self):
        """Publish what the dashboard cannot work out from the board's output alone."""
        recording = self.state in ("holding", "web", "timed")
        self.dash.update(waiting=self.waiting_for_answer(), confirm=self.confirming(), shell=self.tail.rstrip().endswith(b"$"),
                         mic="sending" if self.sending else "recording" if recording else "idle",
                         level=self.level, seconds=len(self.speech) / RATE if recording else 0.0)

    def commands(self):
        """Requests from the dashboard: push-to-talk, a typed answer, start a conversation."""
        while True:
            try:
                name, payload = self.dash.commands.get_nowait()
            except Exception:
                return
            if name == "ptt_start" and self.state == "idle":
                if self.waiting_for_answer():
                    self.begin("web")
                else:
                    self.dash.note("Sister is not waiting for an answer yet.")
            elif name == "ptt_stop" and self.state == "web":
                self.finish()
            elif name == "send":
                text = str(payload.get("text", "")).replace("\n", " ").strip()[:300]
                if text and (self.waiting_for_answer() or self.confirming()):
                    self.write_serial(b"\x15" + text.encode() + b"\n")
                elif text:
                    self.dash.note("Sister is not waiting for an answer yet.")
            elif name == "start":
                if not self.tail.rstrip().endswith(b"$"):
                    self.write_serial(b"\x03")
                    time.sleep(0.3)
                    self.write_serial(b"\x03")
                    time.sleep(0.5)
                mode = payload.get("mode")
                self.write_serial(b"\x15" + (CLASSIC_CMD if mode == "classic" else START_CMD if mode == "sample" else self.start_cmd))

    def send(self, speech):
        seconds = len(speech) / RATE
        note(f"heard {seconds:.1f} s; sending to the board ({len(speech) // 1024} kB)...")
        self.write_serial(b"\x15u\n")
        deadline = time.monotonic() + 4
        while b"receiving audio" not in self.tail[-120:] and time.monotonic() < deadline:
            if select.select([self.serial], [], [], 0.1)[0]:
                self.read_serial()
        encoded = base64.b64encode(speech)
        self.write_serial(f"FMT ulaw {RATE}\n".encode())
        for start in range(0, len(encoded), 76):
            self.write_serial(encoded[start:start + 76] + b"\n")
            self.read_mic()           # keep the microphone pipe drained
        self.write_serial(f"END {hashlib.sha256(speech).hexdigest()}\n".encode())

    # --- keyboard --------------------------------------------------------------
    def key(self, data):
        for byte in data:
            ch = bytes([byte])
            if ch == b"\x1d":         # Ctrl-]
                return False
            if self.state in ("timed", "web"):
                continue
            if ch == b" ":
                if self.state == "idle":
                    if self.waiting_for_answer():
                        self.begin("pending")
                    else:
                        self.write_serial(ch)
                else:
                    if self.state == "pending":
                        self.state = "holding"
                        os.write(1, b"\r\n\x1b[1m  [laptop] recording... release SPACE when you finish\x1b[0m")
                    self.last_repeat = time.monotonic()
            elif self.state == "pending":   # space then another key: ordinary typing
                self.cancel()
                self.write_serial(b" " + ch)
            elif self.state == "idle":
                self.write_serial(ch)
        return True

    def tick(self):
        now = time.monotonic()
        if self.state == "pending" and now - self.pressed > TAP_WINDOW:
            self.cancel()
            self.write_serial(b" ")
        elif self.state == "holding" and (now - self.last_repeat > RELEASE_GAP or len(self.speech) > MAX_SPEECH):
            self.finish()
        elif self.state == "timed" and now > self.timed_until:
            self.finish()
        elif self.state == "web" and len(self.speech) > MAX_SPEECH:
            self.finish()

    def injected(self):
        """Other programs can write to .sister_console/inject: bytes go to the board;
        a line 'PTT <seconds>' records for that long, as if SPACE were held."""
        try:
            data = os.read(self.fifo, 4096)
        except BlockingIOError:
            return
        if not data:
            return
        timed = re.fullmatch(rb"PTT (\d+(?:\.\d+)?)\s*", data)
        if timed:
            self.begin("timed")
            self.timed_until = time.monotonic() + float(timed[1])
            note(f"recording for {timed[1].decode()} s (requested by a script)")
        else:
            self.write_serial(data)

    def run(self, start):
        if start:
            self.write_serial(b"\n")
            deadline = time.monotonic() + 1.5
            while time.monotonic() < deadline:
                if select.select([self.serial], [], [], 0.1)[0]:
                    self.read_serial()
            if self.waiting_for_answer():
                note("Sister is already running on the board")
            elif self.tail.rstrip().endswith(b"$"):
                self.write_serial(self.start_cmd)
            else:
                note("the board is not at a shell prompt; log in or finish what is running, then start Sister")
        note(f"microphone is on. Hold SPACE to talk, release to send. Ctrl-] quits. Dashboard: http://127.0.0.1:{self.dash.port}")
        while True:
            ready = select.select([0, self.serial, self.mic.stdout, self.fifo], [], [], 0.05)[0]
            if self.serial in ready:
                self.read_serial()
            if self.mic.stdout in ready:
                self.read_mic()
            if self.fifo in ready:
                self.injected()
            if 0 in ready and not self.key(os.read(0, 64)):
                return
            self.tick()
            self.commands()
            self.sync()
            if self.mic.poll() is not None:
                note("the microphone stopped (ffmpeg exited); typing still works")
                self.mic = subprocess.Popen(["sleep", "86400"], stdout=subprocess.PIPE)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start", action="store_true")
    parser.add_argument("--port")
    parser.add_argument("--mic", default="0", help="avfoundation audio device index (default 0)")
    parser.add_argument("--classic", action="store_true",
                        help="start the earlier four-step voice demo instead of the SAMPLE history interview")
    parser.add_argument("--web-port", type=int, default=8765, help="dashboard port on 127.0.0.1 (default 8765)")
    args = parser.parse_args()
    ports = sorted(glob.glob("/dev/cu.usbserial-*"))
    port = args.port or (ports[1] if len(ports) > 1 else None)   # the second port is the Linux console
    if not port:
        sys.exit("no board serial port found; is the micro-USB debug cable plugged in?")
    console = Console(port, args.mic, args.web_port, args.classic)
    saved = termios.tcgetattr(0)
    try:
        tty.setraw(0)
        console.run(args.start)
    finally:
        termios.tcsetattr(0, termios.TCSADRAIN, saved)
        console.mic.terminate()
        print("\nconsole closed; Sister is still running on the board.")


if __name__ == "__main__":
    main()
