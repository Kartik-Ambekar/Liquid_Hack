"""
dashboard.py - local status page for the Sister laptop console.

Served by tools/sister_console.py at http://127.0.0.1:8765 (loopback only). Everything it
shows is parsed from what the board prints on the serial cable, plus the laptop
microphone state. No external assets, standard library only. It is a view and a remote
control for the demo; all inference and every triage decision stay on the board.
"""

import json
import queue
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
LOCAL = ("127.0.0.1", "localhost")


class Dashboard:
    def __init__(self, port=8765):
        self.port = port
        self.lock = threading.Lock()
        self.commands = queue.Queue()
        self.events, self.choices = [], []
        self.phase, self.cont, self.linebuf, self.log = "connecting", False, "", ""
        self.flags = {"waiting": False, "confirm": False, "shell": False, "mic": "idle", "level": 0.0, "seconds": 0.0}
        self.last_board_output = 0.0
        handler = type("Handler", (Handler,), {"dash": self})
        self.server = ThreadingHTTPServer(("127.0.0.1", port), handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def add(self, kind, text, **extra):
        self.events.append({"n": len(self.events) + 1, "kind": kind, "text": text, "t": time.strftime("%H:%M:%S"), **extra})

    def feed(self, data):
        """Board output, as bytes, in arrival order."""
        text = ANSI.sub("", data.decode("utf-8", "replace")).replace("\r", "")
        with self.lock:
            self.last_board_output = time.time()
            self.log = (self.log + text)[-8000:]
            self.linebuf += text
            while "\n" in self.linebuf:
                line, self.linebuf = self.linebuf.split("\n", 1)
                self.on_line(line)

    def on_line(self, line):
        t = line.rstrip()
        s = t.strip()
        choice = re.match(r"\s+(\d+)\. (.+)", t)
        if t.startswith("SISTER: "):
            self.add("sister", t[8:])
            self.choices, self.cont, self.phase = [], True, "speaking"
        elif choice:
            self.choices.append({"n": choice[1], "label": choice[2]})
            self.cont = False
        elif t.startswith("YOU> "):
            typed = t[5:].strip()
            self.cont = False
            if typed and typed.lower() != "u":
                label = next((c["label"] for c in self.choices if c["n"] == typed), typed)
                self.add("you", label, how="typed")
                self.phase = "thinking"
        elif "What Sister heard:" in t:
            self.add("you", t.split("heard:", 1)[1].strip().strip('"'), how="voice")
            self.phase = "thinking"
        elif "receiving audio" in t or "transcribing on the board" in t:
            self.phase, self.cont = "transcribing", False
        elif "Interview outcome:" in t:
            self.add("decision", "Interview outcome: " + t.split("outcome:", 1)[1].strip(), rule="")
            self.cont = False
        elif "DECISION (by rule" in t:
            found = re.search(r"rule ([\w-]+)\): (.+)", t)
            self.add("decision", found[2] if found else s, rule=found[1] if found else "")
            self.cont = False
        elif "asking the text model" in t:
            self.phase, self.cont = "thinking", False
        elif "with the vision model" in t:
            self.add("note", s)
            self.phase, self.cont = "looking", False
        elif s.startswith("[spoken by") or s.startswith("[LiquidAI"):
            self.add("metric", s.strip("[]"))
            self.cont = False
        elif s.startswith(("Could not reliably", "could not", "the recording was damaged", "This answer belongs", "Invalid answer", "explanation unavailable", "(could not speak",
                           "handover note", "audit log:")):
            self.add("note", s)
            self.cont = False
        elif s.startswith(("----", "====", "scans:", "last log lines", "{")) or "@" in t[:20]:
            self.cont = False
        elif self.cont and s and self.events and self.events[-1]["kind"] == "sister":
            self.events[-1]["text"] += "\n" + s

    def update(self, **flags):
        with self.lock:
            self.flags.update(flags)

    def note(self, text):
        with self.lock:
            self.add("note", text)

    def snapshot(self, since):
        with self.lock:
            f = self.flags
            if f["mic"] != "idle":
                phase = f["mic"]
            elif f["confirm"]:
                phase = "confirm"
            elif f["waiting"]:
                phase = "waiting"
            elif f["shell"]:
                phase = "stopped"
            else:
                phase = self.phase
            return {"phase": phase, "mic": f["mic"], "level": f["level"], "seconds": round(f["seconds"], 1),
                    "running": not f["shell"] and phase != "connecting",
                    "choices": ([{"n": "y", "label": "Yes, that is what I said"}, {"n": "n", "label": "No, let me answer again"}]
                                if f["confirm"] else self.choices if f["waiting"] else []),
                    "events": self.events[since:], "seq": len(self.events), "log": self.log[-4000:],
                    "tail": self.events[-1] if self.events else None,
                    "board_seen": round(time.time() - self.last_board_output, 1) if self.last_board_output else None}


class Handler(BaseHTTPRequestHandler):
    dash = None

    def log_message(self, *args):
        pass

    def local(self):
        origin = self.headers.get("Origin")
        return (self.headers.get("Host", "").split(":")[0] in LOCAL
                and (not origin or urlparse(origin).hostname in LOCAL))

    def reply(self, body, content_type="application/json", status=200):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self.local():
            return self.reply(b"forbidden", "text/plain", 403)
        url = urlparse(self.path)
        if url.path == "/state":
            since = int(parse_qs(url.query).get("since", ["0"])[0])
            return self.reply(json.dumps(self.dash.snapshot(since)).encode())
        if url.path == "/":
            return self.reply(PAGE.encode(), "text/html; charset=utf-8")
        self.reply(b"not found", "text/plain", 404)

    def do_POST(self):
        if not self.local():
            return self.reply(b"forbidden", "text/plain", 403)
        raw = self.rfile.read(min(int(self.headers.get("Content-Length") or 0), 4096))
        try:
            payload = json.loads(raw or b"{}")
        except ValueError:
            payload = {}
        name = {"/ptt/start": "ptt_start", "/ptt/stop": "ptt_stop", "/send": "send", "/start": "start"}.get(self.path)
        if not name:
            return self.reply(b"not found", "text/plain", 404)
        self.dash.commands.put((name, payload))
        self.reply(b'{"ok": true}')


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sister console</title>
<style>
:root{--bg:#0c1117;--panel:#141b24;--line:#263242;--text:#e6edf3;--dim:#8b98a8;--sister:#3fb8af;--you:#f0616d;--warn:#f5b041;--ok:#4cc38a}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:15px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
header{display:flex;gap:8px;align-items:center;padding:12px 18px;border-bottom:1px solid var(--line);flex-wrap:wrap}
h1{font-size:17px;margin:0 10px 0 0;font-weight:650}
h2{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--dim);margin:0 0 10px;font-weight:600}
.pill{padding:3px 10px;border-radius:999px;border:1px solid var(--line);color:var(--dim);font-size:12.5px;white-space:nowrap}
.pill.on{color:var(--ok);border-color:var(--ok)}.pill.off{color:var(--you);border-color:var(--you)}
.spacer{flex:1}
button{font:inherit;color:var(--text);background:#1c2633;border:1px solid var(--line);border-radius:8px;padding:7px 12px;cursor:pointer}
button:hover{border-color:var(--dim)}button.primary{background:var(--sister);border-color:var(--sister);color:#06201e;font-weight:600}
main{display:grid;grid-template-columns:minmax(0,1.3fr) minmax(0,1fr);gap:14px;padding:14px 18px;align-items:start}
@media(max-width:880px){main{grid-template-columns:1fr}}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px;margin-bottom:14px}
.stage{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.turn{border-radius:12px;border:1px solid var(--line);padding:16px 12px;text-align:center;opacity:.4;transition:opacity .2s,border-color .2s}
.turn.active{opacity:1}.turn.sister.active{border-color:var(--sister)}.turn.you.active{border-color:var(--you)}
.who{font-weight:650;margin-bottom:10px}
.bars{display:flex;gap:5px;justify-content:center;align-items:center;height:64px}
.bars i{width:7px;height:10px;border-radius:4px;background:var(--sister)}
.speaking .bars i{animation:talk .9s ease-in-out infinite}
.bars i:nth-child(2){animation-delay:.12s}.bars i:nth-child(3){animation-delay:.24s}.bars i:nth-child(4){animation-delay:.36s}.bars i:nth-child(5){animation-delay:.48s}
@keyframes talk{0%,100%{height:10px}50%{height:56px}}
.working .bars i{animation:think 1.1s linear infinite;height:10px}
@keyframes think{0%,100%{opacity:.25}50%{opacity:1}}
.micwrap{height:64px;display:flex;align-items:center;justify-content:center}
.mic{width:44px;height:44px;border-radius:50%;background:#2a3544;transition:transform .08s,background .15s}
.recording .mic{background:var(--you);box-shadow:0 0 0 8px rgba(240,97,109,.22)}
.sending .mic{background:var(--warn)}
.state{margin-top:10px;min-height:22px;color:var(--dim)}
.turn.active .state{color:var(--text)}
#hold{margin-top:12px;width:100%;padding:12px;font-weight:600;user-select:none;touch-action:none}
#hold.down{background:var(--you);border-color:var(--you);color:#fff}
#talk{max-height:46vh;overflow:auto;display:flex;flex-direction:column;gap:8px}
.msg{padding:9px 12px;border-radius:10px;max-width:92%;white-space:pre-wrap;overflow-wrap:anywhere}
.msg small{display:block;font-size:11.5px;color:var(--dim);margin-bottom:2px}
.msg.sister{background:#12302e;border:1px solid #1d4a47;align-self:flex-start}
.msg.you{background:#3a1b20;border:1px solid #5a2a31;align-self:flex-end}
.msg.metric,.msg.note{font-size:12px;color:var(--dim);padding:0 4px;max-width:100%}
.msg.decision{align-self:stretch;max-width:100%;font-weight:650;border:1px solid var(--warn);background:#2e2410}
.msg.decision.emergency{border-color:var(--you);background:#3a1b20}
.msg.decision.self{border-color:var(--ok);background:#12301f}
#choices{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:10px}
form{display:flex;gap:8px}input{flex:1;font:inherit;color:var(--text);background:#0f151d;border:1px solid var(--line);border-radius:8px;padding:8px 10px;min-width:0}
pre{margin:0;max-height:38vh;overflow:auto;font:12px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace;color:#b7c2cf;white-space:pre-wrap;overflow-wrap:anywhere}
.hint{color:var(--dim);font-size:12.5px;margin-top:8px}
</style></head><body>
<header>
  <h1>Sister console</h1>
  <span class="pill" id="p-board">board: ...</span>
  <span class="pill" id="p-sister">Sister: ...</span>
  <span class="pill" id="p-mic">laptop mic: ...</span>
  <span class="pill">inference: on the board (Dragonwing IQ-9075)</span>
  <span class="spacer"></span>
  <button id="start" class="primary">Start conversation</button>
</header>
<main>
  <section>
    <div class="card">
      <h2>Whose turn</h2>
      <div class="stage">
        <div class="turn sister" id="t-sister"><div class="who">Sister</div>
          <div class="bars"><i></i><i></i><i></i><i></i><i></i></div><div class="state" id="s-sister">&nbsp;</div></div>
        <div class="turn you" id="t-you"><div class="who">You</div>
          <div class="micwrap"><div class="mic" id="mic"></div></div><div class="state" id="s-you">&nbsp;</div></div>
      </div>
      <button id="hold">Hold SPACE (or hold this button) to talk</button>
      <div class="hint">Your voice is recorded on the laptop, sent down the serial cable, and transcribed on the board.</div>
    </div>
    <div class="card"><h2>Conversation</h2><div id="talk"></div></div>
  </section>
  <section>
    <div class="card"><h2>Answer without speaking</h2><div id="choices"></div>
      <form id="form"><input id="text" placeholder="Type an answer, or s 1 to attach a sample scan" autocomplete="off"><button>Send</button></form></div>
    <div class="card"><h2>Board log (serial cable)</h2><pre id="log"></pre></div>
  </section>
</main>
<script>
const $ = id => document.getElementById(id);
let seq = 0, down = false, lastLog = "";
const post = (path, body) => fetch(path, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body || {})}).catch(() => {});
const SISTER = {speaking: "Speaking...", transcribing: "Transcribing your voice...", thinking: "Working on the board...", looking: "Looking at the scan...", connecting: "Connecting...", stopped: "Not running"};
function pill(el, text, on) { el.textContent = text; el.className = "pill " + (on === null ? "" : on ? "on" : "off"); }
function render(s) {
  pill($("p-board"), s.board_seen === null ? "board: no output yet" : "board: connected over serial", s.board_seen !== null);
  pill($("p-sister"), s.running ? "Sister: running" : "Sister: not running", s.running);
  pill($("p-mic"), "laptop mic: " + (s.mic === "idle" ? "ready" : s.mic), s.mic === "recording" ? false : true);
  $("start").textContent = s.running ? "New conversation" : "Start conversation";
  const sisterBusy = ["speaking", "transcribing", "thinking", "looking"].includes(s.phase);
  const ts = $("t-sister"), ty = $("t-you");
  ts.className = "turn sister" + (sisterBusy ? " active " + (s.phase === "speaking" ? "speaking" : "working") : "");
  $("s-sister").textContent = SISTER[s.phase] || " ";
  const yours = ["waiting", "recording", "sending", "confirm"].includes(s.phase);
  ty.dataset.phase = s.phase;
  ty.className = "turn you" + (yours ? " active" : "") + (s.phase === "recording" ? " recording" : s.phase === "sending" ? " sending" : "");
  $("s-you").textContent = s.phase === "recording" ? "Recording " + s.seconds.toFixed(1) + " s - release to send"
    : s.phase === "sending" ? "Sending to the board..." : s.phase === "waiting" ? "Your turn: hold SPACE and talk"
    : s.phase === "confirm" ? "Is that what you said? Press Y or N" : " ";
  $("mic").style.transform = s.phase === "recording" ? "scale(" + (1 + Math.min(1, s.level) * 0.7).toFixed(2) + ")" : "scale(1)";
  const talk = $("talk");
  for (const e of s.events) {
    const d = document.createElement("div");
    d.className = "msg " + e.kind;
    d.dataset.n = e.n;
    if (e.kind === "decision") {
      d.className += /emergency/i.test(e.text) ? " emergency" : /self/i.test(e.text) ? " self" : "";
      d.textContent = e.rule ? "Decision by rule " + e.rule + ": " + e.text : e.text;
    } else {
      if (e.kind === "sister" || e.kind === "you") {
        const who = document.createElement("small");
        who.textContent = (e.kind === "sister" ? "Sister" : "You (" + e.how + ")") + " - " + e.t;
        d.appendChild(who);
      }
      d.appendChild(document.createTextNode(e.text));
    }
    talk.appendChild(d);
  }
  if (s.events.length) talk.scrollTop = talk.scrollHeight;
  // a Sister message can gain more lines after it is first shown; refresh that bubble's text
  if (s.tail && s.tail.kind === "sister") {
    const el = talk.querySelector('[data-n="' + s.tail.n + '"]');
    if (el && el.lastChild.nodeValue !== s.tail.text) { el.lastChild.nodeValue = s.tail.text; talk.scrollTop = talk.scrollHeight; }
  }
  seq = s.seq;
  const ch = $("choices");
  const key = JSON.stringify(s.choices);
  if (ch.dataset.key !== key) {
    ch.dataset.key = key; ch.textContent = "";
    for (const c of s.choices) { const b = document.createElement("button"); b.textContent = (/^\d+$/.test(c.n) ? c.n + ". " : "") + c.label; b.onclick = () => post("/send", {text: c.n}); ch.appendChild(b); }
  }
  if (s.log !== lastLog) { lastLog = s.log; const pre = $("log"); pre.textContent = s.log; pre.scrollTop = pre.scrollHeight; }
}
async function tick() {
  try { const r = await fetch("/state?since=" + seq); render(await r.json()); }
  catch (e) { pill($("p-board"), "console not reachable", false); }
  setTimeout(tick, 250);
}
const typing = () => document.activeElement && document.activeElement.tagName === "INPUT";
function press() { if (!down) { down = true; $("hold").classList.add("down"); post("/ptt/start"); } }
function release() { if (down) { down = false; $("hold").classList.remove("down"); post("/ptt/stop"); } }
document.addEventListener("keydown", e => { if (e.code === "Space" && !typing()) { e.preventDefault(); if (!e.repeat) press(); } });
document.addEventListener("keyup", e => { if (e.code === "Space" && !typing()) { e.preventDefault(); release(); } });
document.addEventListener("keydown", e => { if (!typing() && $("t-you").dataset.phase === "confirm" && (e.key === "y" || e.key === "n")) post("/send", {text: e.key}); });
window.addEventListener("blur", release);
$("hold").addEventListener("pointerdown", e => { e.preventDefault(); press(); });
["pointerup", "pointerleave", "pointercancel"].forEach(n => $("hold").addEventListener(n, release));
$("hold").addEventListener("keydown", e => e.preventDefault());
$("form").addEventListener("submit", e => { e.preventDefault(); const t = $("text").value.trim(); if (t) post("/send", {text: t}); $("text").value = ""; $("text").blur(); });
$("start").addEventListener("click", () => { $("talk").textContent = ""; post("/start"); $("start").blur(); });
tick();
</script></body></html>
"""
