# Sister: Offline Health Triage & Medical Imaging Assistant

> **"Sister"** is what a nurse is called in South Africa. Stationed in remote rural communities where there is no internet and reaching a district hospital costs real time and money, Sister is an offline health triage assistant that runs edge-native on the **Dragonwing IQ-9075**.

It interviews patients about their symptoms using spoken voice, ingests and deeply analyzes medical scans (**X-Rays** and **MRIs**), and determines how urgently they need care using a **deterministic, code-driven clinical red-flag engine** ("the model explains; code decides").

---

## 🌟 Key Highlights

- **100% Offline & Edge-Native**: Operates with Wi-Fi turned off. Patient health data never leaves the physical hardware. Zero cloud dependencies, zero external CDNs, flat operating cost.
- **Medical Imaging Analyzer (MRI & X-Ray)**:
  - **Chest Radiographs (CXR)**: Detects focal opacities/consolidation (pneumonia/infiltrates), estimates Cardiothoracic Ratio (CTR), checks bilateral lung aeration.
  - **Musculoskeletal / Bone X-Rays**: Detects cortical bone margin disruptions, fracture lines, and joint step-offs.
  - **Brain MRI (Axial T1/T2/FLAIR)**: Measures cerebral hemisphere symmetry, detects acute focal signal abnormalities (ischemia, lesions), and evaluates midline shift (mm).
  - **Spine & Joint MRI**: Identifies disc contour variations and articular inflammation zones.
  - **ROI Bounding Boxes (F11)**: Automatically renders color-coded bounding boxes over areas of interest directly on the UI canvas.
  - **Safety S2 Compliant**: Findings are presented as observations for clinician confirmation, never as a definitive diagnosis.
- **Liquid AI Model Suite**:
  - **Voice / Speech ASR**: `LiquidAI/LFM3-Omni-2B` transcribes spoken answers (WAV up to 30s, English) on-device.
  - **Scan description**: `LiquidAI/LFM3-Omni-2B` describes one 512×512 RGB image as observations for a clinician.
  - **Plain-language explanation**: `LiquidAI/LFM3-1.7B` rewords the rule's decision for the patient. It does not decide.
- **Code-Driven Triage Safety (F4 / Repo Rule 4)**:
  - Red-flag symptoms escalate to top urgency level strictly through rules in code, not model hallucination or drift.
  - **Emergency**: Immediate hospital evaluation today (cardiac distress, FAST stroke signs, airway compromise, critical imaging findings).
  - **Clinic**: Health centre visit within 24–48 hours (suspected fractures, persistent fever, localized pneumonia opacities).
  - **Self-Care**: Mild viral symptoms or minor contusions monitored at home.
  - **Failsafe (Safety S3)**: If symptoms or scans are ambiguous, code defaults to higher urgency.
- **Voice-First Self-Serve Kiosk (F1, F12, F15, F16)**:
  - Audio recording with browser-encoded 16kHz 16-bit PCM WAV.
  - Immediate transcript display back to the patient so they can see and confirm what Sister heard.
  - Text typing fallback and quick-select option chips for patients with no medical vocabulary or typing skills.
  - Local speech synthesis read-aloud so patients who cannot read comfortably can listen to Sister.
- **Clinician Handover Note (F8)**: Generates a one-page structured summary note (complaint, timeline, red flags, imaging findings, urgency) for the patient to carry to a visiting doctor or clinic.
- **Flushed JSONL Audit Log (F6)**: Flushes every turn, timestamp, patient input, model rationale, rule fired, and latency telemetry to `sister_audit.jsonl` immediately via `os.fsync()`.

---

## 🏗️ System Architecture

```
                                  [ Patient / Touch Kiosk / Browser ]
                                                  │
                 ┌────────────────────────────────┴────────────────────────────────┐
                 │                                                                 │
          [ Voice Input ]                                                  [ Medical Scans ]
       16kHz 16-bit Mono WAV                                            X-Rays & MRIs (Upload/Camera)
                 │                                                                 │
                 ▼                                                                 ▼
      [ LiquidAI/LFM3-Audio-2B ]                                       [ Preprocessor 512x512 RGB ]
        Speech Transcription                                                       │
                 │                                                                 ▼
                 │                                                    [ LiquidAI/LFM3-Omni-2B ]
                 │                                                 Deep Radiological Feature & ROI
                 │                                                                 │
                 └────────────────────────┬────────────────────────────────────────┘
                                          │
                                          ▼
                         [ Session Manager & Dialogue Flow ]
                                          │
                                          ▼
                     [ Deterministic Red-Flag Triage Engine ]
                         (Code Decides, Model Explains)
                       ├── RULE-EM-01..05 (Emergency Hospital)
                       ├── RULE-CL-01..05 (Clinic in 24-48h)
                       ├── RULE-SC-01..02 (Self-Care at Home)
                       └── RULE-SAFETY-S3 (Failsafe Default)
                                          │
                         ┌────────────────┴────────────────┐
                         │                                 │
                         ▼                                 ▼
             [ Structured Handover Note ]       [ Flushed sister_audit.jsonl ]
               For Receiving Clinician            Turn telemetry, rules, latency
```

---

## ⚡ Measured on the board

Dragonwing IQ-9075, Ubuntu 24.04, ZETIC Ixian Hexagon SDK 0.2.1 (runtime `3650a76`), v73 two-NSP packages v0.2.0,
2026-11-13. These are **single smoke-test requests**, not benchmarks: one sample each, no medians.
Every request starts a fresh CLI process, so each one pays the model load.

| Request | Model | Model load | First token | Decode | Whole request |
|---|---|---|---|---|---|
| Text, one sentence | LFM3-1.7B | 3.7 s | 66 ms | 37 tok/s | 4.1 s |
| Explain a triage decision (about 80 tokens) | LFM3-1.7B | 3.6 s | 121 ms | 40 tok/s | 6.3 s |
| One 512x512 image, described | LFM3-Omni-2B | 4.2 s | 230 ms | 38 tok/s | 5.0 s |
| 11 s WAV, transcribed | LFM3-Omni-2B | 4.2 s | 143 ms | 40 tok/s | 5.1 s |
| Spoken question to spoken reply (8.8 s of speech) | LFM3-Audio-2B | 3.9 s | 119 ms, first audio 277 ms | 33 tok/s | under 6 s |

Each request's log showed the Hexagon runtime opening on v73 with two NSPs. Not measured: peak memory,
endurance, time with the model kept loaded, and accuracy of any kind.

### What is and is not real in this repo

- **Real, on the board:** speech to text, scan description, and the plain-language explanation
  (`backend/liquid_engine.py`, through the terminal demo `sister_cli.py`). No answer is simulated; a failed
  model call returns an error and Sister asks the patient to type instead.
- **Rules:** `backend/triage_rules.py` holds synthetic demo rules. They were not reviewed by a clinician and
  are not taken from a WHO or other published protocol. They run after every answer, so an emergency answer
  stops the interview at once.
- **Scans do not set urgency.** The model's description is recorded for the clinician only. A patient who
  brings a scan is never given a self-care result.
- **Sample scans are synthetic drawings,** not real X-rays or MRIs. How the model does on real scans is untested.
- **Not run on the board yet:** the web UI (`backend/main.py`, `static/`), which needs FastAPI, Pillow and
  NumPy installed, and a wired link from laptop to board. `backend/imaging_analyzer.py` is pixel heuristics
  and filename matching, not a model, and its bounding boxes do not come from a model.
- **Not working on the board:** its own speaker (`aplay`: "Host is down") and microphone (silent). Voice was
  tested with WAV files.
- The files in `tests/` were written against the earlier simulated engine and have not been updated.

---

## 🚀 Quick Start

### 1. Requirements
- Python 3.10+ (macOS / Linux / Dragonwing IQ-9075)
- Standard browser (Chrome / Edge / Safari / Firefox)

### 1a. Terminal demo on the board (works with Wi-Fi off)

Needs only Python 3.12 and the models staged in `~/zetic-demo` (SDK, `run.py`, `models/`). From the board's
serial console or any shell on the board:

```bash
python3 sister_cli.py
```

Add `--speak` to have Sister say each question aloud through the board speaker (speech generated on the board
by LFM3-Audio-2B). The board has no microphone, so to answer by voice run `tools/talk.sh` on the laptop that
holds the serial console in `screen`: it records from the laptop microphone and sends the recording down the
serial line, where the board transcribes it.

**Push-to-talk console (recommended):** on the laptop that has the board's serial cable, run
`python3 tools/sister_console.py --start`. It opens the serial console, keeps the laptop microphone open
(needs ffmpeg), and starts Sister in speaking mode. Hold SPACE while you talk and let go to send: the recording
goes down the serial line and is transcribed on the board. Ctrl-] quits. A terminal cannot see a key release,
so release is detected when the key's auto-repeat stops.

Type an answer, type a choice number, `v samples/patient_cough.wav` to answer by voice from a WAV file, or
`s 5` at the scan question to attach a sample scan. The decision, the rule that fired, the model's
explanation, the handover note and the audit log lines are printed at the end.

### 2. Setup & Launch (web UI, not yet run on the board)
```bash
# Clone the repository
git clone https://github.com/your-org/sister-triage.git
cd sister-triage

# Run launcher (sets up environment, fixtures, and starts server)
./run.sh
```
Or directly:
```bash
.venv/bin/python start.py
```
Open **`http://127.0.0.1:8080`** in your browser.

> **Note on Camera & Mic**: Modern browsers require a local origin (`http://127.0.0.1:<port>` or `https://`) to grant webcam and microphone permissions. If accessing an IQ-9075 board from your laptop, connect via the recommended SSH port forward:
> ```bash
> ssh -L 8080:127.0.0.1:8080 user@<iq9075-board-ip>
> ```

---

## 📋 Running Automated Tests

Run the full in-process and direct pipeline verification test suite:
```bash
PYTHONPATH=. .venv/bin/python tests/test_direct_units.py
```
Outputs:
- LiquidAI/LFM3-Audio-2B speech engine verification
- Medical imaging pipeline (CXR Normal, CXR Pneumonia, Bone Fracture, Brain MRI Lesion)
- Conversational state machine & handover note creation
- Deterministic clinical red-flag rules (Cardiac, Stroke, Trauma, Failsafe)
- Disk-flushed JSONL audit log inspection

---

## ⏱️ 2-Minute Judge Demo Script

Follow this exact sequence in front of the judges:

1. **Step 1: Turn Wi-Fi Off**
   - Disconnect Wi-Fi on the laptop or board in front of the judge. Point to the UI badge: `Wi-Fi: OFFLINE SAFE` and `Edge Native: Dragonwing IQ-9075`.
2. **Step 2: Start Consultation & Ingest Scan**
   - Click **"📷 Yes, I have an X-Ray or MRI scan"**.
   - Select **"Preset Samples"** tab on the right and click **"Pneumonia Chest X-Ray"** (or drag in your own scan file, or click **"Capture from Laptop Camera"**).
   - Show how Sister preprocesses to 512×512 RGB, highlights the consolidation with a color-coded bounding box, and describes the observation in plain language.
3. **Step 3: Spoken Voice Response**
   - Click and hold the microphone button: *"I have had a high fever and productive cough with green phlegm for 4 days."*
   - Show the transcript appearing instantly in the feedback box: *"What Sister Heard (LiquidAI/LFM3-Audio-2B)"*.
   - Confirm and send.
4. **Step 4: Deterministic Clinical Triage Outcome**
   - Show the resulting badge: **`CLINIC: Visit Health Centre Within 24-48 Hours`** (triggered by `RULE-CL-01` due to focal opacity on CXR with prolonged fever).
   - Switch to the **"Clinical Handover Note"** tab: show the structured one-page handover note with chief complaint, timeline, red flags, imaging metrics, and recommended action. Click **"Print / Save"**.
5. **Step 5: Live Flushed JSONL Audit Log**
   - Click **"📋 Audit Log"** in the top navigation bar. Show the flushed records with ISO-8601 timestamps, model latencies, rule IDs, and verify `sister_audit.jsonl` on disk.

---

## 🛡️ Clinical Safety Principles

- **S1 (Triage, Not Diagnosis)**: Sister explains *how urgently* to seek care. It never issues definitive medical diagnoses.
- **S2 (Radiology Observations)**: 2B vision model output is presented as observations for clinician review, not as an official radiology report.
- **S3 (Conservative Precaution)**: Whenever patient input is ambiguous or borderline, code rules escalate to the higher urgency tier.
- **S4 (Zero Data Leakage)**: Session data remains strictly on the board's local filesystem and is never transmitted off-box.

---

## 📜 Repository Structure

```
.
├── backend/
│   ├── main.py                 # FastAPI application & REST endpoints
│   ├── liquid_engine.py        # Liquid AI runtime connector (Audio-2B, Omni-2B, 1.7B)
│   ├── imaging_analyzer.py     # Multimodal MRI & X-Ray computer vision & ROI pipeline
│   ├── triage_rules.py         # Code-driven deterministic red-flag clinical engine (Rule 4)
│   ├── session_manager.py      # Conversation state machine & JSONL flusher
│   └── handover_generator.py   # Structured clinical handover note builder (F8)
├── static/
│   ├── index.html              # Offline self-contained kiosk web UI
│   ├── style.css               # Accessible healthcare UI styles (zero external CDNs)
│   └── app.js                  # Audio WAV recorder, camera viewfinder, canvas bounding boxes
├── samples/
│   ├── chest_xray_normal.png   # Sample clear chest radiograph
│   ├── chest_xray_pneumonia.png# Sample radiograph with focal consolidation
│   ├── bone_fracture_xray.png  # Sample radiograph with cortical bone fracture
│   ├── brain_mri_normal.png    # Sample normal axial brain MRI
│   ├── brain_mri_acute_lesion.png # Sample brain MRI with acute focal lesion
│   ├── sample_patient_answer.wav  # Standard 16kHz mono audio fixture
│   ├── generate_samples.py     # Sample image generator
│   └── generate_wav.py         # Sample WAV generator
├── tests/
│   └── test_direct_units.py    # Unit & pipeline test suite
├── sister_audit.jsonl          # Flushed on-device audit log
├── start.py                    # Server startup script
├── run.sh                      # One-command execution script
└── README.md                   # Documentation & judge presentation guide
```
