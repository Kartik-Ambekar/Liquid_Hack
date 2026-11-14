# Sister: clinical-protocol-grounded offline interview handoff

Date: 2026-11-13 (Pacific). Audience: the next coding agent and team.
Repository inspected at `0148690ddbfa57bcbd73811a83ae04c7b22add94`.

> **Status: proposed engineering design for an unvalidated hackathon prototype.**
> This document does not supply clinical rules, establish diagnostic accuracy, or
> validate Sister for patient use. Deterministic code is reproducible; it is not
> automatically clinically correct. No WHO endorsement is implied.

## 1. Inputs, provenance, and intended scope

This handoff synthesizes the team discussion in
[Scegliere idea hackathon](chatgpt-conversation://6af7c6f8-78c0-83ed-a13f-8a77a3c2548e),
the attached **Sister requirements, Draft 3, 2026-11-13 18:55 PT**, and the
current repository. The attachment was read from the conversation export; it is
not a tracked requirements file in this checkout. Its references to a parent
`AGENTS.md`, `docs/judging.md`, and vendor wrappers belong to the original
hackathon context; those files are absent here. No repository `AGENTS.md` was
found. Do not infer that all Draft 3 platform assertions are implemented here.

Draft 3 decisions: rural disconnected community; **patient operating alone**;
board-side inference on Dragonwing IQ-9075; voice-first English answers with
transcript confirmation; guided interview; deterministic urgency rules; handoff.
Earlier responder/ship/mining stories were alternatives, not the final user
choice. The patient's literacy, accessibility, and ability to act on instructions
remain unresolved.

**Proposed narrower promise:** collect symptoms in everyday language, exercise a
small explicitly labeled simulated escalation workflow, and prepare a structured
handoff for a professional, offline. Do not demonstrate that Sister can safely
tell patients to stay home. Draft 3's three-tier urgency scale was still proposed,
not a clinically reviewed decision. No diagnosis, prescription, fine-tuning,
longitudinal records, queues, video, or MRI-volume interpretation in this scope.

## 2. Repository map and concrete gaps

| Existing file | Observed role | Next-agent implication |
| --- | --- | --- |
| `README.md` | Requirements F/S identifiers, architecture, demo and benchmark claims | Claims are documentation, not proof of model execution or clinical validity. Preserve it during this handoff; reconcile claims in a separately scoped implementation change. |
| `backend/main.py` | FastAPI routes and image/audio/session integration | Enforce validation at boundaries; distinguish actual runtime from fixture mode. |
| `backend/session_manager.py` | Greeting/ingest → complaint → duration → severity → complete; JSONL flush | Triage currently occurs at severity, rather than after every relevant answer. Proposed immediate interruption and correction handling need implementation. |
| `backend/triage_rules.py` | Keyword-based rules, image urgency, clinic/self-care outcomes | Not a source-mapped WHO protocol. Negation, context and missingness need review; do not treat existing rule IDs as clinical evidence. |
| `backend/liquid_engine.py` | GenieX/CLI attempts plus fallbacks | Audio fallback selects a canned transcript from duration; text fallback echoes the prompt after a simulated delay. TTFT is derived from elapsed time and fallback throughput includes a constant. These are not measured model capabilities. |
| `backend/imaging_analyzer.py` | Image/filename heuristics, observations, ROIs and urgency flags | Not evidence of validated radiology inference. Keep unvalidated image-derived urgency outside the proposed safety decision path. |
| `backend/handover_generator.py` | Note from session and decision | Avoid turning unassessed signs into “none”; record unknowns and actual runtime provenance. Current template asserts on-device execution without independently proving it. |
| `static/` | Local browser interface, recording/camera and rendering | Retain typed fallback, confirmation, short questions and accessible status. Verify speech output works without downloaded voices/services. |
| `samples/`, `tests/`, `sister_audit.jsonl` | Generated fixtures, pipeline checks and existing log | Synthetic checks demonstrate software behavior only. Do not publish real patient data or overwrite the tracked log during documentation verification. |

Existing `confidence=1.0` for a deterministic rule is not a probability of clinical
correctness. Existing README latency numbers, MRI capabilities and “100% offline”
claims were **not verified on Dragonwing in this task**. A green fixture test does
not establish real ASR, vision, NPU use, or clinical safety.

## 3. Reference sources and scope cautions

Links below were checked against official WHO descriptions. They are candidates
for careful protocol selection, not interchangeable ready-to-run patient flows.

| Source | Intended relevance | Scope caution |
| --- | --- | --- |
| [WHO IMAI district clinician manual, 2011](https://www.who.int/publications/i/item/9789241548281) and [WHO overview, 2012](https://www.who.int/publications/i/item/imai-district-clinician-manual-hospital-care-adolescents-and-adults) | Adolescent/adult illness in resource-constrained district hospital care | Written for clinicians; hospital procedures cannot be delegated to an untrained patient. Identify exact edition/module and country adaptation. IMAI materials differ; do not silently substitute a district manual for a primary-care module. |
| [WHO IMCI chart booklet, 2014](https://pmnch.who.int/resources/publications/i/item/9789241506823) | Structured child assessment by health professionals | Separate young-infant and child pathways; not an adult protocol. Historical booklet is not necessarily current for every topic: [2019 young-infant update](https://www.who.int/publications/i/item/9789241516365) illustrates why version checks matter. Exclude pediatric flow from an adult-only demo. |
| [WHO–ICRC Basic Emergency Care, 2018](https://www.who.int/publications-detail-redirect/9789241513081) | Systematic initial assessment in limited-resource settings | Training for first-contact healthcare providers, not unsupervised self-service. Useful design reference; copying assessments requiring clinical skill is inappropriate. |
| [WHO SMART Guidelines](https://www.who.int/teams/digital-health-and-innovation/smart-guidelines) and [published artifacts](https://smart.who.int/) | Traceable translation into digital workflows, data dictionaries, decision logic and testable requirements | A digitization approach and domain-specific artifacts, not a universal triage protocol or safety certification. Check whether an applicable artifact actually exists. |

Before encoding clinical content: choose population, setting, intended operator,
jurisdiction, source version and exact section/page; verify updates and reuse
terms; obtain appropriate clinical review and document every adaptation. Patient
wording, unavailable observations, referral access and emergency instructions
need local review. Do not invent thresholds, dosages, clinical branch conditions,
or emergency telephone numbers. This handoff intentionally contains none.

## 4. Proposed architecture: language understands; protocol decides

```text
Typed answer / local ASR → confirmed transcript → bounded LLM fact extraction
  → schema + evidence validation → versioned session facts
  → deterministic protocol engine → approved question OR escalation OR handoff
  → fixed safety wording / constrained plain-language rendering → local audit
```

The LLM extracts symptoms, timing and reported history, preserves uncertainty,
and may rephrase an engine-selected question without changing its meaning.
It must not select urgency, invent missing answers, diagnose, prescribe, choose
clinical branches, or supply new medical advice. Retrieval/prompting alone does
not enforce a protocol. Fine-tuning is out of scope and would not guarantee safety.
A static questionnaire baseline helps demonstrate the model's specific value:
understanding varied natural descriptions and mapping them to explicit facts.

### Proposed state-machine contract (not a clinical pathway)

1. `START`: establish scope and show prototype status; offer an immediate help
   control. Safety must not wait for optional document upload.
2. `SAFETY_SCREEN`: request the next approved item in a reviewed specification.
3. `COLLECT`: record complaint, onset and required contextual answers one at a
   time, as selected by the engine.
4. `CLARIFY`: resolve ambiguous/contradictory answers using approved wording.
   Unknown remains unknown; bounded clarification prevents endless interviews.
5. `ESCALATE`: interrupt ordinary interview when an authorized encoded condition
   fires. Fixed, locally approved action text must work without model generation.
6. `HANDOFF`: summarize reported facts, missingness and rule provenance. An
   incomplete assessment is not a negative screen.
7. `ERROR_OR_OUT_OF_SCOPE`: stop unsupported decisions and show the reviewed
   fallback/help route. A technical failure is not itself a clinical diagnosis.

Re-evaluate after every accepted answer or correction, not only at completion.
Record old and new values; an escalation cannot silently disappear because the
model rephrases a response. Define reviewed reset/downgrade policy. Engine owns
state, permitted transitions, required fields, precedence, question IDs and
terminal actions. LLM output is untrusted data, including “ignore the rules”.

Each future protocol artifact should contain ID/version, population/operator,
source edition/section, reviewed question text and answer vocabulary, required
facts, explicit predicates, precedence, missing/contradictory-input behavior,
terminal action templates, reviewer/status, and matching synthetic test IDs.
Until reviewed, use isolated **synthetic demo rules**, visibly labeled as such;
do not label them WHO rules or silently enable them for real patients.

## 5. Proposed JSON contract

This is a **new extraction contract**, not the current API or a clinical data
standard. JSON Schema Draft 2020-12 below validates shape, not truth. The engine
supplies IDs/versions and timestamps separately, and rejects unknown field IDs
against the active protocol dictionary. No model-generated decision field exists.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Sister proposed extraction v0.1",
  "type": "object",
  "additionalProperties": false,
  "required": ["turn_id", "facts", "needs_clarification"],
  "properties": {
    "turn_id": {"type": "string", "minLength": 1},
    "facts": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["field_id", "value", "status", "evidence", "source"],
        "properties": {
          "field_id": {"type": "string", "minLength": 1},
          "value": {"type": ["string", "number", "boolean", "null"]},
          "status": {"enum": ["reported", "denied", "unknown", "contradictory"]},
          "evidence": {"type": "string"},
          "source": {"enum": ["typed_answer", "confirmed_transcript"]}
        }
      }
    },
    "needs_clarification": {"type": "boolean"}
  }
}
```

Example extraction for “I have felt dizzy since yesterday; I don't know why”:

```json
{
  "turn_id": "demo-turn-1",
  "facts": [
    {"field_id": "reported_symptom", "value": "dizzy", "status": "reported", "evidence": "felt dizzy", "source": "typed_answer"},
    {"field_id": "onset_text", "value": "yesterday", "status": "reported", "evidence": "since yesterday", "source": "typed_answer"}
  ],
  "needs_clarification": true
}
```

Illustrative field IDs only; no urgency follows from this example. Enforce source
substring evidence, per-field types/units/enums, nullable unknowns, negation,
subject/temporality and contradictory-value checks in application code. Do not
infer an absolute onset time without the session date/time context. Unmentioned
facts are unassessed, not denied. No numeric LLM confidence establishes safety.

Engine-owned session envelope should include `schema_version`, `session_id`,
`protocol_id`, `protocol_version`, `review_status`, `state`, `question_id`,
`facts`, `missing_fields`, `contradictions`, `triggered_rule_ids`, `action_id`,
`runtime_mode`, `model_version`, `errors`, and measured timing. Keep image
attachments/observations in a separate provenance section, excluded from decision
inputs for this proposed MVP. Log state transitions and evidence references;
render the handoff from accepted structured data rather than a free-form model
summary. Never accept model-supplied engine fields as authoritative.

## 6. Safety, uncertainty and privacy requirements

- Ask one short question at a time; provide “I don't know”, skip, correction and
  typed fallback. Confirm ASR before accepting it; confirmation alone does not
  prove transcription accuracy. Do not interpret silence as “no”.
- Reject malformed, empty, reasoning-only, extra-field or unsupported model
  outputs. Use capped time/tokens and at most one bounded retry, then approved
  template clarification/help. Escalation rendering must not depend on a retry.
- Unknown or contradictory critical inputs cannot justify reassurance. Draft 3
  proposed defaulting “more urgent”; exact fallback/precedence still needs
  clinical review. Do not assume the existing generic CLINIC fallback is enough.
- Image upload is optional and cannot delay safety handling. No automatic image
  diagnosis, quantitative radiology claim, ROI validity claim, or image-driven
  urgency in the proposed narrowed demo. Clearly mark synthetic fixtures.
- Separate patient report, ASR transcript, extracted fact, image observation and
  rule outcome. Handoff lists what was asked, what was not, uncertainty, and source
  versions. “No rule fired” does not mean no emergency or that self-care is safe.
- Use synthetic patients for public demos/logs. Minimize identifiers, bound file
  uploads and retention, restrict log access and define deletion. Local storage
  reduces cloud exposure but is not automatic privacy compliance. A laptop UI
  receives patient information over the local link; avoid a literal “data never
  leaves the box” claim when this is the architecture.
- Any real deployment needs clinical evaluation for the intended users and locale,
  accessibility/usability work, referral planning and applicable governance review.
  The hackathon cannot establish these outcomes.

## 7. Synthetic evaluation plan and honest metrics

Expected clinical actions must come from a reviewed, versioned specification.
Before that exists, test only labeled simulated workflow behavior. Split extractor
checks from pure rule tests and end-to-end tests so extraction failures are visible.

| Scenario | Expected engineering behavior |
| --- | --- |
| Explicit severe breathing-difficulty report, including in an early turn | Preserve evidence; if a selected reviewed/simulated escalation condition matches, interrupt immediately, without extra interview or image delay. |
| “I don't know”, silence, unclear severity, incomplete answer | Preserve unknown; clarify or enter approved fallback; no invented negative. |
| Negated sign, historical symptom, someone else's symptom | Distinguish denial, temporality and subject; avoid keyword-only false positives. |
| Patient corrects an earlier denial | Version facts and re-evaluate; retain audit trail and visible change. |
| Indirect wording / paraphrases | Extract only supported facts or clarify; compare against labeled facts. |
| Contradictory answers | Mark conflict and follow specified policy, not last-write-wins reassurance. |
| Uploaded X-ray / synthetic MRI, with misleading filename | Isolate image observations; filename and unvalidated vision cannot set urgency. |
| Invalid JSON, empty output, timeout, missing model, failed ASR | Bounded retry/template fallback; explicit error/runtime mode; never canned invented patient testimony. |
| Prompt injection in patient text | Reject attempted engine-field/control changes; retain normal protocol control. |
| Wi-Fi and Ethernet disconnected, restart, local log inspection | Complete supported local workflow; verify no cloud dependency and log persistence/error visibility. |
| Unsupported population or language | Clearly mark out of scope; do not reuse adult/English rules indiscriminately. |

Report dataset version, number of cases, expected labels, model/runtime settings,
failures and actual numerator/denominator for each metric:

- **Extraction precision/recall and field accuracy**, including negation, unknown,
  timing, subject and correction errors; show ASR errors separately.
- **Escalation/red-flag recall** on labeled synthetic positive cases; also false
  escalation rate on negatives. Small synthetic sets do not estimate clinical safety.
- **Protocol adherence**: engine actions/transitions matching the specified oracle;
  test all branches, missingness policies and interruption behavior.
- **Schema validity**, fallback/retry rate, completion rate, handoff factual fidelity.
- **Actual on-board performance**: cold load vs warm inference, ASR, extraction,
  whole-turn p50/p95, peak memory and observed accelerator use. Measure TTFT from
  first token events and tokens/sec from actual tokenizer counts; do not derive
  them from arbitrary elapsed fractions or constants.
- **Offline evidence**: real board/runtime/model identifiers, disconnected-network
  rehearsal and local input/decision/action/error records. UI badges are not proof.

Compare free-language extraction with a fixed questionnaire baseline. Never label
synthetic fixture success, heuristic imaging output, or fallback timing “clinical
validation” or a measured LiquidAI benchmark. No new tests or measurements were
run as part of this documentation-only handoff.

## 8. Dragonwing / LiquidAI constraints and demo plan

Draft 3 reported these platform constraints; verify against the actual supplied
SDK, drive and board before promising them:

- IQ-9075 runs inference; laptop is local display/input/camera only. Stage assets
  by **copying**, not moving, from the supplied USB drive. Confirm model inventory.
- Proposed split: resident GenieX LFM3-1.7B for text; separate ZETIC/CLI Omni-2B
  for ASR/image. Draft 3 expected Omni for voice; current code names Audio-2B.
  Decide from a real successful board invocation, not the model-name constant.
- Reported wrapper: one 512×512 RGB image per call, text output, no image/audio
  mixing or tool calling; no verified bounding boxes. Preprocess locally.
- Voice: English WAV, at most 30 seconds; browser converts locally, no CDN.
  Current code/UI claim 16 kHz PCM; verify exact SDK sample format with vendor
  fixture. Text fallback is essential for noise, permissions and absent models.
- Historical wrapper load figure (~3.3 seconds per call) was from an older SDK,
  not a current measurement. Voice can require ASR plus text extraction/rendering;
  separate reloads may dominate the two-minute budget. Verify memory coexistence.
- Use localhost SSH forwarding over an isolated USB/local link for microphone and
  camera secure-context access. Keep control alive when external networking is cut.
- Draft 3 wrapper had no speech output. Browser speech synthesis is a separate
  capability whose local/offline availability must be tested; do not assume it.

Discussion rubric (transcribed from event context, **not independently verified
here**): edge-native value 25%, originality 20%, execution 20%, usefulness 15%,
performance/efficiency 10%, demo 10%. Event details should be rechecked with the
organizers: November 13, 2026, two-minute demo plus one question; submission
8:00–8:30 PM Pacific and judging/build cutoff reported as 8:15 PM; public GitHub
and Arduino Project Hub write-up/code links required.

Proposed demo budget: 15s problem/scope, 60s for a few varied answers, 20s handoff,
15s local audit/runtime evidence, 10s buffer. Disconnect board Wi-Fi **and Ethernet**
in front of judges while retaining isolated control. Use synthetic data, rehearse
with room noise, stage a labeled backup recording. Add image/voice only if measured
rehearsal fits; otherwise demonstrate text first and label absent features honestly.

Pitch: the model converts natural patient descriptions to auditable facts; explicit
code controls a narrow interview and simulated escalation; the workflow continues
without external services. Privacy and resilience are plausible advantages;
lower total cost, faster inference, user demand and better health outcomes remain
hypotheses. Explain the specific disconnected setting rather than assuming all
rural areas lack internet or that Starlink makes reliability irrelevant.

## 9. Implementation priorities and unresolved decisions

### P0 — honest, narrow end-to-end prototype

1. Confirm real board model invocation; visibly separate fixture mode and failures.
   Remove fabricated transcripts/telemetry from any claimed model demonstration.
2. Agree one population and one narrow workflow; write versioned protocol artifact
   and test oracle. Keep unreviewed demo logic explicitly synthetic.
3. Add strict extraction validation, evidence/unknown tracking and engine-owned
   transitions. Check for interruption after each answer and before optional ingest.
4. Implement fixed help/escalation templates and structured handoff/audit; avoid
   self-care reassurance and unvalidated image-based decisions in the narrowed demo.
5. Rehearse text path offline and measure actual timings; record known failures.

### P1 — only after P0 works

Real local ASR with confirmed transcript, typed fallback, correction handling,
accessibility review, and verified offline voice output if available. Optional
image attachment may be shown separately without medical claims or urgency impact.

### Defer

Bounding boxes, MRI analysis/volumes, diagnoses, prescriptions, always-on sensing,
fine-tuning, broad pediatric pathways, multilingual claims and patient records.

| Decision / owner to assign | Recommended next action / unresolved point |
| --- | --- |
| Clinical scope/reviewer | Adult-only screening was proposed, not agreed as a validated pathway. Who selects exact guidance, adaptation and approval? |
| Operator/accessibility | Draft 3 chose patient alone. Can they read English text, confirm transcripts and obtain help? If scope changes to a trained responder, document that explicitly. |
| Urgency/fallback semantics (Draft Q5) | Resolve emergency/clinic/self-care conflict; define uncertainty, out-of-scope, correction and downgrade policies with review. This document does not set them. |
| Model route (Q3) / board owner | Confirm Audio vs Omni availability, exact CLI contract, GenieX residence, memory and actual board execution. |
| Interview/triage owner | Map proposed schema/state machine to session API and rule module without silently treating legacy rules as approved. |
| Ingest owner | Keep observations separate; decide whether to omit imaging from judged core loop. |
| Voice/accessibility owner (Q8) | Verify recording format, room-noise behavior, model absence fallback and local speech availability. |
| Demo/submission owner (Q7) | Verify event rules/deadlines, stage samples/backup, collect genuine timing evidence and prepare both submission links. |
| Privacy/deployment owner | Define retention, local-link exposure, emergency/referral resources and eventual clinical evaluation plan. |

**Acceptance for the next coding change:** explicit runtime mode, no fabricated
patient facts, validated extraction shape/evidence, deterministic traceable
transitions, early interruption in synthetic tests, preserved unknowns/corrections,
image isolation, structured handoff, and measured disconnected-board rehearsal.
These are engineering acceptance criteria, not authorization for real clinical use.
