"""
session_manager.py - Conversation Flow & Flushed JSONL Audit Logger for Sister
Fulfills:
  - F1: Sister leads interview, 1 question at a time, plain language, quick choices
  - F2: First step offers to ingest X-ray / MRI or notes
  - F3: Session ends with triage result (urgency, reasons, next steps)
  - F4: Deterministic red flags evaluated via ClinicalTriageEngine
  - F5: Ingested X-ray / MRI folded into session context
  - F6: Flushed JSONL logging after every turn (input, output, rule, decision, error)
  - S1: Triages, never diagnoses ("how urgently to seek care", never "you have X")
"""

import os
import json
import time
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime

from backend.triage_rules import ClinicalTriageEngine, TriageDecision
from backend.handover_generator import HandoverNoteGenerator
from backend.liquid_engine import LiquidAIEngine

AUDIT_LOG_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "sister_audit.jsonl"))

class SessionManager:
    """
    Manages active triage sessions and flushed JSONL logging.
    """

    _sessions: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def create_session(cls) -> Dict[str, Any]:
        session_id = f"SIST-{uuid.uuid4().hex[:6].upper()}"
        session = {
            "session_id": session_id,
            "start_time": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
            "current_step": "GREETING_INGEST",
            "turn_index": 0,
            "symptoms": [],
            "duration": "",
            "severity": "",
            "answers": {},
            "imaging_findings": None,
            "triage_decision": None,
            "handover_note": None,
            "history": []
        }
        cls._sessions[session_id] = session
        
        # Log session start to flushed JSONL
        cls._flush_log({
            "event": "SESSION_INITIALIZED",
            "session_id": session_id,
            "timestamp": session["start_time"],
            "hardware": "Dragonwing IQ-9075",
            "models": ["LiquidAI/LFM3-Audio-2B", "LiquidAI/LFM3-Omni-2B", "LiquidAI/LFM3-1.7B"]
        })
        
        return session

    @classmethod
    def get_session(cls, session_id: str) -> Optional[Dict[str, Any]]:
        return cls._sessions.get(session_id)

    @classmethod
    def get_initial_prompt(cls) -> Dict[str, Any]:
        """
        Step 0 (F2): Offers to add existing documents / scans or start interview.
        """
        return {
            "step": "GREETING_INGEST",
            "sister_message": "Hello, I am Sister, your offline health triage assistant. Do you have an X-ray, MRI, or doctor's note you would like me to check first?",
            "spoken_text": "Hello, I am Sister, your health assistant. Do you have an X-ray or MRI scan to show me before we begin?",
            "choices": [
                {"id": "yes_image", "label": "📷 Yes, I have an X-Ray or MRI scan", "action": "open_ingest"},
                {"id": "no_image", "label": "🩺 No, let's start the questions", "action": "skip_ingest"}
            ],
            "allows_voice": True,
            "allows_text": True,
            "status": "in_progress"
        }

    @classmethod
    def process_turn(cls, session_id: str, user_input: str, input_type: str = "text", voice_meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        session = cls.get_session(session_id)
        if not session:
            session = cls.create_session()
            session_id = session["session_id"]

        session["turn_index"] += 1
        turn_start = time.perf_counter()
        current_step = session["current_step"]

        sister_response = {}
        rule_fired = "NONE"
        triage_outcome = None
        error_msg = None

        try:
            # STEP 0: GREETING_INGEST
            if current_step == "GREETING_INGEST":
                lower = user_input.lower()
                if "yes" in lower or "x-ray" in lower or "mri" in lower or "image" in lower or "scan" in lower:
                    sister_response = {
                        "step": "AWAITING_INGEST",
                        "sister_message": "Please upload your X-ray or MRI file, or hold it in front of the camera so I can inspect it.",
                        "spoken_text": "Please upload your scan or hold it to the camera.",
                        "choices": [
                            {"id": "camera_btn", "label": "📸 Use Camera", "action": "open_camera"},
                            {"id": "upload_btn", "label": "📁 Upload Scan File", "action": "open_upload"},
                            {"id": "skip_btn", "label": "Skip and continue interview", "action": "skip_ingest"}
                        ],
                        "status": "awaiting_image"
                    }
                    session["current_step"] = "AWAITING_INGEST"
                else:
                    # Proceed to Chief Complaint
                    sister_response = cls._get_step_chief_complaint()
                    session["current_step"] = "CHIEF_COMPLAINT"

            # STEP 1: CHIEF COMPLAINT
            elif current_step in ["CHIEF_COMPLAINT", "AWAITING_INGEST"]:
                # Record symptom
                session["symptoms"].append(user_input)
                session["answers"]["chief_complaint"] = user_input
                sister_response = cls._get_step_duration(user_input)
                session["current_step"] = "DURATION"

            # STEP 2: DURATION
            elif current_step == "DURATION":
                session["duration"] = user_input
                session["answers"]["duration"] = user_input
                sister_response = cls._get_step_severity(session["symptoms"])
                session["current_step"] = "SEVERITY"

            # STEP 3: SEVERITY & RED FLAGS
            elif current_step == "SEVERITY":
                session["severity"] = cls._parse_severity(user_input)
                session["answers"]["severity_description"] = user_input
                
                # Perform deterministic triage evaluation (F4)
                decision = ClinicalTriageEngine.evaluate(session)
                session["triage_decision"] = decision.__dict__
                rule_fired = decision.rule_fired
                triage_outcome = decision.urgency_level

                # Generate Handover Note (F8)
                handover = HandoverNoteGenerator.generate(session, decision)
                session["handover_note"] = handover

                sister_response = {
                    "step": "COMPLETE",
                    "sister_message": (
                        f"Thank you for sharing your symptoms. "
                        f"Based on clinical triage rules, your recommended urgency is: **{decision.urgency_label}**.\n\n"
                        f"**Why:** {decision.summary_reason}\n\n"
                        f"**Next Steps:** {decision.recommended_action}"
                    ),
                    "spoken_text": f"Your triage result is: {decision.urgency_label}. {decision.summary_reason} {decision.recommended_action}",
                    "triage_decision": decision.__dict__,
                    "handover_note": handover,
                    "choices": [
                        {"id": "download_note", "label": "📄 Save Handover Note", "action": "download_handover"},
                        {"id": "restart", "label": "🔄 Start New Patient Consultation", "action": "new_session"}
                    ],
                    "status": "completed"
                }
                session["current_step"] = "COMPLETE"

        except Exception as e:
            error_msg = str(e)
            sister_response = {
                "step": "ERROR",
                "sister_message": "An error occurred during evaluation. Defaulting to clinic review for safety.",
                "spoken_text": "An error occurred. Please visit your local clinic for safety.",
                "status": "error"
            }

        turn_duration = round((time.perf_counter() - turn_start) * 1000, 1)

        # Build turn log and flush immediately to JSONL (F6)
        log_entry = {
            "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
            "session_id": session_id,
            "turn_index": session["turn_index"],
            "input_type": input_type,
            "patient_input": user_input,
            "voice_meta": voice_meta or {},
            "step": session["current_step"],
            "model_text": sister_response.get("sister_message"),
            "rule_fired": rule_fired,
            "triage_decision": triage_outcome,
            "latency_ms": turn_duration,
            "error": error_msg
        }
        cls._flush_log(log_entry)

        # Update session history
        session["history"].append({
            "turn": session["turn_index"],
            "patient": user_input,
            "sister": sister_response.get("sister_message")
        })

        return sister_response

    @classmethod
    def attach_imaging_analysis(cls, session_id: str, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """
        Attaches MRI / X-ray findings to the session (F5) and folds into conversation.
        """
        session = cls.get_session(session_id)
        if not session:
            session = cls.create_session()
            session_id = session["session_id"]

        session["imaging_findings"] = analysis
        session["answers"]["imaging_modality"] = analysis.get("scan_type")
        session["answers"]["imaging_observation"] = analysis.get("primary_observation")

        # Sister describes observation in plain language (F5, S2)
        message = (
            f"I have inspected your {analysis.get('scan_type')}.\n\n"
            f"**Observation:** {analysis.get('primary_observation')}\n\n"
            f"I have recorded these observations to guide our interview. "
            f"What primary discomfort or symptoms led you to take this scan?"
        )
        spoken = f"I have inspected your {analysis.get('scan_type')}. {analysis.get('primary_observation')}. What symptoms are you feeling?"

        session["current_step"] = "CHIEF_COMPLAINT"
        session["turn_index"] += 1

        response = {
            "step": "CHIEF_COMPLAINT",
            "sister_message": message,
            "spoken_text": spoken,
            "imaging_analysis": analysis,
            "choices": [
                {"id": "severe_pain", "label": "Severe localized pain / swelling", "action": "select_symptom"},
                {"id": "cough_breathing", "label": "Trouble breathing / chest tightness", "action": "select_symptom"},
                {"id": "numbness_weakness", "label": "Weakness, dizziness, or numbness", "action": "select_symptom"},
                {"id": "follow_up", "label": "Routine follow-up / checkup", "action": "select_symptom"}
            ],
            "allows_voice": True,
            "allows_text": True,
            "status": "imaging_attached"
        }

        # Flush JSONL log
        cls._flush_log({
            "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
            "session_id": session_id,
            "turn_index": session["turn_index"],
            "event": "IMAGING_ATTACHED",
            "modality": analysis.get("modality"),
            "scan_type": analysis.get("scan_type"),
            "primary_observation": analysis.get("primary_observation"),
            "urgency_flag": analysis.get("urgency_flag"),
            "model": "LiquidAI/LFM3-Omni-2B"
        })

        return response

    @classmethod
    def _get_step_chief_complaint(cls) -> Dict[str, Any]:
        return {
            "step": "CHIEF_COMPLAINT",
            "sister_message": "What is the main problem bothering you today?",
            "spoken_text": "What is the main problem bothering you today?",
            "choices": [
                {"id": "c1", "label": "🫀 Chest pain or pressure", "action": "select_symptom"},
                {"id": "c2", "label": "🫁 Cough or difficulty breathing", "action": "select_symptom"},
                {"id": "c3", "label": "🌡️ High fever or chills", "action": "select_symptom"},
                {"id": "c4", "label": "🦴 Fall, injury, or severe bone pain", "action": "select_symptom"},
                {"id": "c5", "label": "🤢 Severe stomach pain or vomiting", "action": "select_symptom"},
                {"id": "c6", "label": "🧠 Headache, dizziness, or weakness", "action": "select_symptom"}
            ],
            "allows_voice": True,
            "allows_text": True,
            "status": "in_progress"
        }

    @classmethod
    def _get_step_duration(cls, symptom: str) -> Dict[str, Any]:
        return {
            "step": "DURATION",
            "sister_message": f"I understand. How long have you had this {symptom}?",
            "spoken_text": f"How long have you had this {symptom}?",
            "choices": [
                {"id": "d1", "label": "Just started today (few hours)", "action": "select_duration"},
                {"id": "d2", "label": "For 2 to 3 days", "action": "select_duration"},
                {"id": "d3", "label": "For about a week", "action": "select_duration"},
                {"id": "d4", "label": "More than 2 weeks", "action": "select_duration"}
            ],
            "allows_voice": True,
            "allows_text": True,
            "status": "in_progress"
        }

    @classmethod
    def _get_step_severity(cls, symptoms: List[str]) -> Dict[str, Any]:
        symp_text = " ".join(symptoms).lower()
        if "chest" in symp_text or "breath" in symp_text:
            msg = "Is the chest pain spreading to your arm or jaw, or are you having severe shortness of breath or cold sweats?"
        elif "fall" in symp_text or "bone" in symp_text or "injury" in symp_text:
            msg = "Are you unable to bear weight or move the bone, or is there visible deformity or open bleeding?"
        elif "head" in symp_text or "dizz" in symp_text:
            msg = "Do you have any face drooping, slurred speech, or weakness in your arms or legs?"
        else:
            msg = "How severe is your discomfort right now, and does it prevent you from normal daily activities?"

        return {
            "step": "SEVERITY",
            "sister_message": msg,
            "spoken_text": msg,
            "choices": [
                {"id": "s1", "label": "⚠️ Severe with danger signs / unbearable", "action": "select_severity"},
                {"id": "s2", "label": "Moderate, noticeable pain/trouble", "action": "select_severity"},
                {"id": "s3", "label": "Mild discomfort only", "action": "select_severity"}
            ],
            "allows_voice": True,
            "allows_text": True,
            "status": "in_progress"
        }

    @classmethod
    def _parse_severity(cls, text: str) -> str:
        t = text.lower()
        # Clean out common negations like "no severe", "not severe"
        cleaned = t.replace("no severe", "").replace("not severe", "").replace("no danger", "").replace("not unbearable", "")
        if "severe" in cleaned or "unbearable" in cleaned or "danger" in cleaned or "yes" in cleaned:
            return "severe"
        elif "moderate" in cleaned or "medium" in cleaned:
            return "moderate"
        return "mild"

    @classmethod
    def _flush_log(cls, entry: Dict[str, Any]):
        """
        Immediately writes and flushes JSONL entry to disk (F6).
        """
        try:
            line = json.dumps(entry, ensure_ascii=False) + "\n"
            with open(AUDIT_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(line)
                f.flush()
                os.fsync(f.fileno())
        except Exception as e:
            print(f"[AUDIT LOG ERROR] Failed to flush entry: {e}")

    @classmethod
    def read_audit_log(cls, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Reads recent audit log entries for the UI inspector.
        """
        if not os.path.exists(AUDIT_LOG_FILE):
            return []
        entries = []
        try:
            with open(AUDIT_LOG_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        entries.append(json.loads(line))
        except Exception:
            pass
        return entries[-limit:]
