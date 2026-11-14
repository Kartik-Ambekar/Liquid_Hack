# Sister: requirements

Draft 3, 2026-11-13 18:55 PT (voice first; see section 9). Source: team kickoff conversation plus this repo's rules ([README](../../README.md), [AGENTS.md](../../AGENTS.md), [judging](../../docs/judging.md)).

Status key: **[said]** came from the team conversation. **[repo]** is a hackathon rule or a platform limit. **[proposed]** is a default filled in to close a gap; change it freely. **[open]** needs a team decision.

## 1. What it is

Sister is an offline health triage assistant that runs entirely on a Dragonwing IQ-9075. It is stationed where there is no internet and where reaching a doctor costs real time and money. It interviews the patient about symptoms, takes in any documents they already have (X-rays, doctor's notes), and tells them how urgently they need care. **[said]**

The name: "sister" is what a nurse is called in South Africa. **[said]**

Setting: rural community with no connectivity is the primary story. The in-flight case is the event's metaphor, not our use case. **[said]**

## 2. Why not a cloud API call

Judges ask this first, and edge-native value is 25% of the score. **[repo]**

- There is no network where this is deployed. A cloud model is not slower there, it is absent.
- Health data never leaves the box. No account, no upload, no third party.
- Flat cost per consultation, which matters for a clinic with no budget for per-token billing.

## 3. Users

| Who | Need |
|---|---|
| Patient in a remote community | Find out whether this needs a clinic trip today, this week, or not at all, before paying for the trip |
| The same patient, operating it alone | Self-serve: no health worker present. Sister cannot assume medical vocabulary, confident typing, or any training on the device **[decided]** |
| Receiving clinician | A short, structured handover instead of starting the history from zero **[proposed]** |

## 4. Functional requirements

### Must have (the demo loop)

| ID | Requirement | Source |
|---|---|---|
| F1 | Sister leads the conversation: it asks the questions, one at a time, to draw out symptoms, duration, severity, and relevant history. The patient does not need to know what to say. Plain, non-clinical wording, short questions, and answer choices where possible, because the patient is alone | said, decided |
| F2 | The first step offers to add existing material: "Do you have any documents, X-rays, or notes to add?" If yes, take the ingest path (F5); if no, go straight to the interview | said |
| F3 | The session ends with a triage result: an urgency level, the reasons for it in plain language, and what to do next | proposed |
| F4 | Red-flag symptoms (for example chest pain with breathlessness, heavy bleeding, stroke signs) escalate to the top urgency level through a rule in code, not through model judgement. The model explains; code decides | proposed, repo rule 4 |
| F5 | Ingest one X-ray image supplied by the patient, describe what is visible in plain language, and fold that description into the session. Doctor's notes are a later addition, not tonight's demo | said, decided |
| F12 | Voice first: the patient answers by speaking. Each answer is one recording of up to 30 seconds, transcribed on the board, and the transcript is shown back so the patient can see what Sister heard. English only tonight | decided |
| F6 | Every turn is written to a flushed JSONL log: input, model output, the rule that fired, the triage decision, errors | repo |
| F7 | Everything runs on the board with Wi-Fi off, started from a session that survives the cut (UART or isolated USB-C link) | repo |

### Should have

| ID | Requirement | Source |
|---|---|---|
| F8 | Handover summary: a one-page structured note (complaint, timeline, red flags, documents seen, urgency) the patient can carry to a clinic | proposed |
| F9 | Capture the image from the laptop camera rather than only from a file | said |
| F15 | Typed answers as a fallback for every question, for a noisy room or a failed transcription | proposed |
| F10 | A simple board-hosted web UI over the USB-C link, with all assets served locally. All inference runs on the IQ-9075; the laptop is only a screen, keyboard, and camera | proposed, decided for inference |

### Stretch

| ID | Requirement | Source |
|---|---|---|
| F11 | Bounding boxes drawn on the X-ray around regions of interest | said, unverified |
| F13 | Always-on behaviour: Sister notices a waiting patient or a new file and starts the session unprompted. Not tonight's positioning | proposed |
| F14 | Local languages | proposed |
| F16 | Sister speaks its questions aloud. The repo's wrapper has no speech output, so this would need the vendor SDK directly, or synthesis in the laptop browser, which is off-board | proposed |

## 5. Platform constraints that shape the design

All **[repo]**.

- **Image input is narrow.** The repo's multimodal route (ZETIC wrapper with LFM3-Omni-2B or LFM3-VL-2B) takes one image per request, exactly 512x512 RGB, and returns text. It does not resize. We resize before the call.
- **Bounding boxes are not a verified capability here.** A Liquid AI staff member told us their vision models can box an X-ray in about a second. The wrapper in this repo returns text only, so boxes would have to come back as coordinates in text and be drawn by us. Nothing in the repo confirms this works on this board. Treat F11 as stretch until one test image proves it.
- **Camera pipelines are outside this repo.** Camera capture happens on the laptop (browser), and the frame is sent to the board over the USB-C link. Inference stays on the board.
- **No mixed image and audio in one turn**, and no tool calling, on the ZETIC route.
- **Voice is input only, and it is a transcription step.** The wrapper takes one WAV of up to 30 seconds and returns text using an English speech-recognition prompt. It has no speech output, so Sister's questions appear as text on screen. A voice turn is therefore two model calls: transcribe, then produce the next question.
- **The wrapper reloads the model on every call.** The repo records a median of about 3.3 seconds of loading per call on an older SDK, not re-measured. Two wrapper calls per voice turn would add roughly twice that before any generation. We measure our own number before quoting one.
- **The microphone and camera only work on a local address.** Browsers allow them on `127.0.0.1` but not on a plain `http://<board-ip>` page. Open the UI through the SSH port forward the repo already recommends, so the laptop sees it at `http://127.0.0.1:<port>`.
- **The browser does not record WAV by default.** The page converts the recording to WAV itself, with no CDN library, before sending it to the board. The repo does not state a required sample rate, so match the format of its `samples/asr/jfk.wav` fixture and test with that file first.
- **Two runtimes if we want both.** The reference text path is LFM3-1.7B on GenieX (OpenAI-compatible server, well-trodden). Omni runs through a separate CLI wrapper. See Q3.
- **Every model call is capped and validated.** Empty or reasoning-only answers count as failures, with one retry.
- **Model assets come from the supplied USB drive.** Copy, never move. What is on our drive decides which models are realistic tonight.

## 6. Safety requirements

A health assistant gets asked about this, and "real-world usefulness" is 15%.

- S1. Sister triages; it does not diagnose and does not prescribe. Output wording is "how urgently to seek care", never "you have X". **[proposed]**
- S2. Image findings are presented as observations for a clinician to confirm, not as a reading. A 2B model's view of an X-ray is not a radiology report. **[proposed]**
- S3. When the model's answer fails validation or the session is ambiguous, the result defaults to the more urgent level. **[proposed]**
- S4. Session data stays on the board. Nothing identifying is required to start a session. **[proposed]**

## 7. Demo and submission

- Two minutes, at our table, plus one judge question. No separate pitch slot. **[said, repo]**
- Script: turn Wi-Fi off in front of the judge, run one patient session end to end (spoken answers, one X-ray, triage result), show the JSONL log. Keep it to three or four spoken answers so the turn latency fits in two minutes, and rehearse with the room noise.
- Have local sample data (one X-ray image, one doctor's note photo, a scripted patient) and a backup recording. **[repo]**
- Submit between 8:00 and 8:30 PM: a public GitHub repo link and an Arduino Project Hub post containing the write-up and code. Someone needs an Arduino account signed in before 8:00. **[repo]**
- Measured numbers for our own app go in the app README: time to first token, tokens per second, end-to-end turn time. **[repo]**

## 8. Workstreams

| Stream | Scope | Owner |
|---|---|---|
| Board | Access, NPU packages, GenieX, model from USB, first response, Wi-Fi-off control path | **[open]** |
| Ingest | F2, F5, F9: upload or camera, resize to 512x512, vision call, description into the session | teammate who volunteered **[said]** |
| Voice | F12, F15: record in the page, convert to WAV, transcribe on the board, show the transcript, typed fallback | **[open]** |
| Interview and triage | F1, F3, F4, F6: question flow, red-flag rules, triage result, log | **[open]** |
| Demo and submission | Sample data, script, repo public, Arduino Project Hub post, numbers | **[open]** |

## 9. Decisions

### Decided (18:45)

| Decision | Outcome |
|---|---|
| Operator | The patient alone, self-serve |
| Image step in the demo | X-ray description as observations. Bounding boxes stay stretch until one test image proves them |
| Where the models run | On the Dragonwing IQ-9075, per this repo. Nothing is inferred on the laptop |
| Input | Voice first: spoken answers, transcribed on the board. Typed answers stay as a fallback (decided 18:55) |
| Positioning | Guided session with triage decided by code: Sister leads the interview, red-flag rules set urgency, and it writes the handover note itself. Not an always-on monitor |

### Still open

| # | Decision | Why it matters |
|---|---|---|
| Q3 | Model route. Voice first means an audio-capable model is required, so LFM3-Omni-2B (ears and eyes in one package) is the natural pick. Open part: whether the interview text also goes through Omni, or through LFM3-1.7B on the resident GenieX server | Omni for everything is one model to stage but pays the reload on every call. GenieX for the interview text avoids one reload per turn and is the path board setup brings up anyway. Proposed: Omni for transcription and the X-ray, GenieX for the interview, run one at a time. Confirm Omni is on the USB drive first |
| Q5 | Triage scale. Proposed and not yet objected to: emergency now, clinic within days, self-care at home | Needed before the red-flag rules can be written |
| Q7 | Owners for the board, voice, interview and triage, and demo and submission streams | Only ingest has an owner |
| Q8 | Whether a patient alone can be expected to read Sister's questions on screen, or whether spoken output (F16) is needed for the story to hold | Affects the pitch more than tonight's build; be ready for the judge to ask |

## 10. Out of scope tonight

Diagnosis, prescriptions, patient records across sessions, multi-patient queues, video, MRI volumes (single 2D images only), and any model fine-tuning.
