# Sister SAMPLE questionnaire: coding-agent implementation contract

Version 0.1.0 · 2026-11-13 Pacific · synthetic demonstration only.

## Deliverable and scope

Implement an English adult self-report history intake using the included data and prompts. The 41 possible questions are conditional, not a mandatory 41-question interrogation. This is a proposed adaptation of SAMPLE with a small illustrative safety screen. It is not a validated first-aid protocol, a complete emergency screen, diagnostic system, or an implementation of WHO IITT. The exact wording, routing, population limits and actions need clinical and local review before patient deployment. No medication, physical examination, numeric vital-sign threshold, self-care clearance or clinic waiting interval is supplied.

Use `questionnaire.json` as the source of truth; `QUESTIONNAIRE.md` is its readable rendering. Each question has a stable ID, definition, source and review status. Questions derived from SAMPLE retain that category; DESIGN questions are product proposals. The 18+ limit and broad pregnancy/recent-birth exclusion are product scope choices, not WHO age bands or evidence-based risk cutoffs. The six safety items are intentionally incomplete. For example, injury, poisoning and other emergencies may exist outside them. A negative screen establishes no safe waiting period.

## Exact routing semantics

Evaluate on session start and after each accepted turn, correction or explicit help action. All true terminal conditions preempt ordinary questions, including when a fact was volunteered early. Use this precedence:

1. Explicit Get help now, or any supplied safety field with an affirmative accepted report: latch HELP_NOW and stop ordinary intake. Proposed conservative demo routing; not a severity classifier. Never auto-dismiss a latched action on later denial or model failure.
2. Stop/withdraw consent: STOPPED. Keep a previously latched help notice visible. Offer deletion of saved answers independently.
3. self=no or adult=no: OUT_OF_SCOPE. consent=no: STOPPED. pregnancy_context=yes: OUT_OF_SCOPE. These scope boundaries do not establish low urgency.
4. Follow the ordered question list. A question's `when` array is an AND of equality tests on accepted answered facts. Unknown/declined/ambiguous is never equal to no. Empty `when` is unconditional.
5. Skip an applicable question only when an adequate answer already exists. Evaluate safety fields from every patient answer, regardless of active question. Keep safety definitions in every model request.
6. Unresolved setup, scope or safety answer: offer one explicit clarification, then ASSESSMENT_INCOMPLETE. Refusal may immediately stop the interview; do not pressure the user. Unknown/declined ordinary history: preserve and move on. Ambiguous ordinary history: one clarification, then move on with unresolved status. Count actual displayed clarification attempts, not controller polls.
7. injury_exposure=yes: collect event_details if not already supplied, then OUT_OF_SCOPE. This is history capture, not an instruction to delay emergency help; any help or safety signal preempts it. Poisoning/trauma classification is not implemented.
8. Show the structured record before review_confirmed. yes applies to the current revision only. no opens field selection/correction; cancel returns to the review. New corrections invalidate confirmation and trigger routing again. “Finish without confirming” is an explicit UI exit producing an unconfirmed handoff, never an implicit yes.
9. Once all applicable questions have been answered or exhausted under the rules, show HANDOFF_READY. Never output green, low risk, safe, diagnosis, or “no medical attention needed.”

Global controls, always visible: Get help now, Stop, Correct an answer, View summary. No response timeout may count as a denial. If a person stops responding, the app cannot determine why; retain an incomplete session and the visible help route. No timeout-generated clinical conclusion.

`controller.py` implements a pure routing reference with a synthetic-only constructor and semantic extraction validation. It has no UI, model integration, storage, authentication, or clinical approval mechanism. It does not solve semantic extraction errors. Its status and evidence checks must be supplemented with actual model evaluation. Do not expose it as a patient-ready service.

## Input and model call contract

Use `prompts/extractor_system.txt` as the system message, the schema and the entire field dictionary, followed by a small number of full input/output examples from `examples.json`. Then send the live input as JSON:

- turn_id: unique server-issued ID; echoed exactly.
- current_question: full question object from questionnaire.json.
- field_definitions: IDs, types and definitions; always include all safety fields. For v0.1 the whole dictionary is small enough to try; measure actual context use.
- confirmed_facts: accepted facts needed for context and correction checks; no hidden instructions.
- patient_answer: verbatim typed answer or user-confirmed local ASR transcript.
- input_source: typed_answer or confirmed_transcript.

Use the actual runtime's chat template. Treat constrained JSON decoding as optional until verified on the installed runtime. Start at temperature 0 if supported, bound generation/time, detect truncation, and record exact model/runtime/settings. Token budget must accommodate multiple volunteered facts; start with 1024 output tokens and measure suitability. Do not silently truncate facts or evidence.

Parse strictly, validate schema and semantics, then accept atomically. Reject extra fields, invalid field IDs, duplicate fields, wrong turn ID, unsupported values and evidence not present in the answer. Validate that evidence actually supports the claim: substring presence alone cannot prove that. One repair request may use `repair_system.txt` plus original input and validation codes. Then show a deterministic input-error template and allow typed/choice entry. Never fabricate a transcript or answer. Existing help/escalation persists through errors. Malformed output containing alarming text must not be partially trusted as a clinical result; keep help visible and use a direct safety confirmation path.

Direct choice buttons bypass the LLM and are recorded as explicit patient input. unknown/declined buttons have null values and matching status; yes/no have answered status and the selected value. Keep raw input and provenance. Do not store unconfirmed ASR as a confirmed fact. Do not allow an LLM to write state, action, timestamp, review status or urgency.

The MVP uses stored question text directly. `question_renderer_system.txt` is an optional exact-copy renderer, not an invitation to invent questions. Safety/action messages always come from actions.json. No free-form model summary: build the handoff deterministically from accepted records.

## State, corrections and handoff

Use one anonymous session ID; no patient name is required. Before consent, keep only ephemeral scope answers; persist and flush once consent is obtained. On refusal, discard ephemeral data. Store field ID, status, value, verbatim evidence, turn/source, timestamp and revision. Append correction history instead of silently overwriting it. Different answered values without a clear correction become ambiguous. A yes safety report latches help even if it conflicts with a prior no.

When a parent branch changes, retain historical child answers but mark them inactive in the current summary. E.g., correcting temperature_measured to no makes prior numeric temperature answers inactive. Preserve safety latches independently. A later onset or medication correction invalidates summary confirmation. Make application requests idempotent using turn IDs; block double submits and stale replies, especially when a newer answer has already changed scope or triggered help.

Handoff fields:
- protocol/package version, unreviewed status, real runtime mode and timestamp;
- respondent and declared scope;
- each SAMPLE section, with reported facts and source evidence;
- temperature as reported number/unit/time, or missing values; no severity interpretation;
- safety items actually answered, unresolved items, and triggered routing IDs;
- omitted conditional questions separately from unanswered/declined questions;
- corrections, summary confirmation revision, incomplete/out-of-scope status;
- attachment metadata in a separate section (no image-derived decision input).

Do not describe a normal conversation as a complete clinical assessment. Do not translate absent safety reports into “no red flags.”

## Existing Liquid_Hack integration map

Inspected base in previous handoff: 0148690ddbfa57bcbd73811a83ae04c7b22add94; re-read latest files before editing.

- backend/session_manager.py: replace fixed complaint-duration-severity sequence with controller state and revision tracking; route after every answer.
- backend/liquid_engine.py: wire real extraction/ASR calls, validation and errors. Disable duration-based fake transcription and simulated performance in any actual model demo.
- backend/triage_rules.py: do not quietly combine this proposed flow with legacy self-care/image urgency rules. New mode must have explicit routing provenance.
- backend/handover_generator.py: structured report with unknowns and real runtime provenance.
- backend/main.py/static/: question IDs, choices, transcript confirmation, correction UX and persistent help button. Serve assets locally.
- logs: use a separate synthetic test log; never modify or publish real patient data. Document storage/retention/deletion; local UI links also carry patient data.

## Demo and release checks

Run `python3 -m unittest -v test_controller.py` in this folder. This checks routing, not the model or clinical accuracy. Evaluate examples.json against the real Liquid model separately; expected outputs are authored labels, not observed results. Report field precision/recall, negation/correction/unknown errors, JSON failure rate, missed supplied safety reports, false escalations, p50/p95 latency and fallback rate with denominators. Test paraphrases, silence, noisy ASR, other-person reports, historical symptoms, prompt injection, and longer multi-fact turns. Verify all inference and assets work on Dragonwing with external networking disconnected.

No synthetic test result is clinical validation. Deployment requires review of source currency, scope, missing safety coverage, localization, clinical actions, accessibility and intended-use performance. The absence of a local emergency number is a configuration gap; do not guess a number. This package remains a simulated demo until those issues are resolved.
