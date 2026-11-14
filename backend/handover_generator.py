"""
handover_generator.py - Structured Clinical Handover Note Generator (F8)
Creates a structured one-page handover note for the receiving clinician:
  - Patient Chief Complaint
  - Symptom Timeline & Severity
  - Red Flags Evaluated & Deterministic Rule Trigger
  - Diagnostic Imaging Summary (X-Ray / MRI observations & ROIs)
  - Recommended Triage Level & Clinical Action
  - Full Timestamp and Offline Board Signature
"""

from typing import Dict, Any
from datetime import datetime
from backend.triage_rules import TriageDecision

class HandoverNoteGenerator:
    """
    Generates structured clinical handover note.
    """

    @classmethod
    def generate(cls, session_data: Dict[str, Any], decision: TriageDecision) -> Dict[str, Any]:
        session_id = session_data.get("session_id", "SIST-0001")
        timestamp = session_data.get("start_time", datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC"))
        symptoms = session_data.get("symptoms", [])
        duration = session_data.get("duration", "Not specified")
        severity = session_data.get("severity", "Not specified")
        answers = session_data.get("answers", {})
        imaging = session_data.get("imaging_findings")

        # Format symptoms
        symptoms_str = ", ".join(symptoms) if symptoms else "Unspecified general discomfort"

        # Format imaging section
        imaging_section = "None provided."
        imaging_meta = {}
        if imaging:
            imaging_section = (
                f"Modality: {imaging.get('scan_type', 'X-Ray / MRI')}\n"
                f"- Primary Observation: {imaging.get('primary_observation')}\n"
                f"- Quantitative Metrics: {imaging.get('metrics', {})}\n"
                f"- Suspected Area / ROI: {len(imaging.get('rois', []))} visual zone(s) annotated.\n"
                f"- Clinician Notice: S2 Compliant - Observations for clinician confirmation; not a definitive radiological diagnosis."
            )
            imaging_meta = {
                "scan_type": imaging.get("scan_type"),
                "primary_observation": imaging.get("primary_observation"),
                "metrics": imaging.get("metrics"),
                "rois": imaging.get("rois")
            }

        # Red flags evaluated
        red_flags_str = "\n".join([f"  [!] {rf}" for rf in decision.red_flags]) if decision.red_flags else "  [OK] None identified during interview."

        # Plain text note for clipboard/export
        raw_text = f"""================================================================================
                    SISTER OFFLINE CLINICAL HANDOVER NOTE
================================================================================
Session ID:         {session_id}
Date & Time:        {timestamp}
Host Hardware:      Dragonwing IQ-9075 (Edge-Native Offline)
AI Engine:          Liquid AI (LFM3-Audio-2B, LFM3-Omni-2B, LFM3-1.7B)
Triage Protocol:    Code-Driven Deterministic Red-Flag Triage Engine
--------------------------------------------------------------------------------

1. CHIEF COMPLAINT & PRESENTING HISTORY
   - Reported Symptoms: {symptoms_str}
   - Duration:          {duration}
   - Severity Level:    {severity.capitalize()}
   - Context / Answers: {cls._format_answers(answers)}

2. DIAGNOSTIC IMAGING REVIEW (X-RAY / MRI)
   {imaging_section}

3. CLINICAL TRIAGE ASSESSMENT
   - Urgency Level:     {decision.urgency_level} ({decision.urgency_label})
   - Deterministic Rule: {decision.rule_fired}
   - Red Flags Checked:
{red_flags_str}

4. PLAIN-LANGUAGE PATIENT EXPLANATION
   "{decision.summary_reason}"

5. RECOMMENDED IMMEDIATE CLINICAL ACTION
   {decision.recommended_action}

--------------------------------------------------------------------------------
Notice: Sister is an offline triage assistant stationed in remote facilities.
All inference ran strictly on-device without internet access.
Observations must be validated by the receiving licensed medical practitioner.
================================================================================
"""

        return {
            "session_id": session_id,
            "timestamp": timestamp,
            "urgency_level": decision.urgency_level,
            "urgency_label": decision.urgency_label,
            "color": decision.color,
            "rule_fired": decision.rule_fired,
            "symptoms": symptoms,
            "duration": duration,
            "severity": severity,
            "answers": answers,
            "imaging_meta": imaging_meta,
            "summary_reason": decision.summary_reason,
            "recommended_action": decision.recommended_action,
            "red_flags": decision.red_flags,
            "raw_text": raw_text
        }

    @classmethod
    def _format_answers(cls, answers: Dict[str, Any]) -> str:
        if not answers:
            return "Standard questionnaire completed."
        return "; ".join([f"{k}: {v}" for k, v in answers.items() if not k.startswith("_")])
