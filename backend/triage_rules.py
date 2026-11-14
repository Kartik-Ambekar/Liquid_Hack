"""
triage_rules.py - Deterministic Red-Flag Clinical Triage Engine for Sister
Following Repo Rule 4 & Functional Requirement F4:
"Red-flag symptoms escalate to the top urgency level through a rule in code, 
not through model judgement. The model explains; code decides."
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional

@dataclass
class TriageDecision:
    urgency_level: str  # "EMERGENCY", "CLINIC", "SELF_CARE"
    urgency_label: str  # Plain language title
    color: str          # Hex color for UI badge
    summary_reason: str # Plain language reason for patient
    recommended_action: str # What to do next
    rule_fired: str     # Rule ID that determined the outcome
    red_flags: List[str] # List of red flags detected
    confidence: float   # Confidence score (1.0 = deterministic code rule)

class ClinicalTriageEngine:
    """
    Deterministic clinical triage engine.
    Levels:
      1. EMERGENCY: Immediate care required (hospital / emergency transport today).
      2. CLINIC: Needs medical evaluation within 24 to 48 hours at local health center.
      3. SELF_CARE: Low risk; self-management at home with monitoring instructions.
    """

    @classmethod
    def evaluate(cls, session_data: Dict[str, Any]) -> TriageDecision:
        symptoms = [s.lower() for s in session_data.get("symptoms", [])]
        duration = session_data.get("duration", "").lower()
        severity = session_data.get("severity", "").lower() # mild, moderate, severe
        answers = session_data.get("answers", {})
        imaging_findings = session_data.get("imaging_findings") or {}

        red_flags_detected = []

        # ============================================================
        # 1. EMERGENCY RED FLAGS (Rule ID prefix: RULE-EM)
        # ============================================================

        # RULE-EM-01: Acute Cardiovascular / Chest Pain
        has_chest_pain = any("chest" in s for s in symptoms) or "chest_pain" in answers.values()
        has_severe_dyspnea = any("shortness of breath" in s or "breathing" in s or "breath" in s for s in symptoms)
        has_radiation = any(k in str(answers).lower() for k in ["arm", "jaw", "back pain", "sweating", "cold sweat", "diaphoresis"])
        if has_chest_pain and (severity == "severe" or has_severe_dyspnea or has_radiation):
            red_flags_detected.append("Acute severe chest pain with systemic red flags (cardiac risk)")
            return TriageDecision(
                urgency_level="EMERGENCY",
                urgency_label="Emergency: Seek Immediate Hospital Care",
                color="#EF4444",
                summary_reason="Your chest pain and associated symptoms could indicate an urgent heart or lung issue that requires immediate emergency evaluation.",
                recommended_action="Go immediately to the nearest emergency hospital or call emergency medical transport. Do not drive yourself.",
                rule_fired="RULE-EM-01",
                red_flags=red_flags_detected,
                confidence=1.0
            )

        # RULE-EM-02: Acute Neurological / Stroke (FAST Signs)
        neuro_keywords = ["stroke", "face drooping", "arm weakness", "slurred speech", "sudden confusion", "cannot move arm", "face droop", "paralysis"]
        if any(k in str(answers).lower() or any(k in s for s in symptoms) for k in neuro_keywords):
            red_flags_detected.append("Acute neurological deficit / stroke signs (FAST criteria)")
            return TriageDecision(
                urgency_level="EMERGENCY",
                urgency_label="Emergency: Seek Immediate Hospital Care",
                color="#EF4444",
                summary_reason="Sudden weakness, facial changes, or speech difficulties require immediate emergency assessment for stroke.",
                recommended_action="Go immediately to an emergency hospital right now. Note the exact time these symptoms began for the doctors.",
                rule_fired="RULE-EM-02",
                red_flags=red_flags_detected,
                confidence=1.0
            )

        # RULE-EM-03: Severe Respiratory Compromise / Stridor
        resp_emergency = ["cannot breathe", "stridor", "blue lips", "gasping", "suffocating", "severe breathlessness"]
        if any(k in str(answers).lower() or any(k in s for s in symptoms) for k in resp_emergency) or (has_severe_dyspnea and severity == "severe"):
            red_flags_detected.append("Critical respiratory distress / airway compromise")
            return TriageDecision(
                urgency_level="EMERGENCY",
                urgency_label="Emergency: Seek Immediate Hospital Care",
                color="#EF4444",
                summary_reason="Severe difficulty breathing requires immediate emergency oxygen and clinical support.",
                recommended_action="Seek emergency medical attention immediately. Sit upright and avoid physical exertion.",
                rule_fired="RULE-EM-03",
                red_flags=red_flags_detected,
                confidence=1.0
            )

        # RULE-EM-04: Severe Trauma / Hemorrhage / Shock
        bleeding_keywords = ["heavy bleeding", "coughing blood", "vomiting blood", "gushing blood", "uncontrolled bleeding"]
        if any(k in str(answers).lower() or any(k in s for s in symptoms) for k in bleeding_keywords):
            red_flags_detected.append("Acute significant hemorrhage")
            return TriageDecision(
                urgency_level="EMERGENCY",
                urgency_label="Emergency: Seek Immediate Hospital Care",
                color="#EF4444",
                summary_reason="Significant active bleeding requires rapid emergency intervention to prevent severe blood loss.",
                recommended_action="Apply firm direct pressure to any bleeding area with a clean cloth and seek emergency transport immediately.",
                rule_fired="RULE-EM-04",
                red_flags=red_flags_detected,
                confidence=1.0
            )

        # RULE-EM-05: Critical Imaging Finding (Tension pneumothorax, midline brain shift > 5mm, open/displaced fracture)
        imaging_urgency = imaging_findings.get("urgency_flag", "")
        if imaging_urgency == "EMERGENCY":
            critical_finding = imaging_findings.get("primary_observation", "Critical finding on medical imaging")
            red_flags_detected.append(f"Critical diagnostic imaging finding: {critical_finding}")
            return TriageDecision(
                urgency_level="EMERGENCY",
                urgency_label="Emergency: Seek Immediate Hospital Care",
                color="#EF4444",
                summary_reason=f"The uploaded scan shows an acute concern ({critical_finding}) that needs prompt hospital assessment.",
                recommended_action="Take this scan and your handover note directly to an emergency department or hospital with radiology facilities.",
                rule_fired="RULE-EM-05",
                red_flags=red_flags_detected,
                confidence=1.0
            )

        # ============================================================
        # 2. CLINIC WITHIN 24-48 HOURS (Rule ID prefix: RULE-CL)
        # ============================================================

        # RULE-CL-01: Imaging Finding of Suspected Fracture or Moderate Opacity
        if imaging_urgency == "CLINIC" or imaging_findings.get("detected_modality") in ["X-RAY_BONE", "X-RAY_CHEST", "MRI_BRAIN", "MRI_SPINE", "MRI_JOINT"]:
            finding_text = imaging_findings.get("primary_observation", "Scan finding requiring clinical confirmation")
            if "fracture" in finding_text.lower() or "opacity" in finding_text.lower() or "consolidation" in finding_text.lower() or "lesion" in finding_text.lower():
                red_flags_detected.append(f"Diagnostic imaging finding: {finding_text}")
                return TriageDecision(
                    urgency_level="CLINIC",
                    urgency_label="Clinic: Visit Health Centre Within 24-48 Hours",
                    color="#F59E0B",
                    summary_reason=f"The scan shows notable features ({finding_text}) that require clinical confirmation, proper splinting/treatment, or prescription medication.",
                    recommended_action="Visit your local clinic or health centre today or tomorrow. Bring this phone/kiosk summary with you.",
                    rule_fired="RULE-CL-01",
                    red_flags=red_flags_detected,
                    confidence=0.95
                )

        # RULE-CL-02: Persistent High Fever or Vulnerable Patient
        has_fever = any("fever" in s or "temperature" in s for s in symptoms) or "fever" in str(answers).lower()
        is_prolonged = any(k in duration for k in ["3 days", "4 days", "5 days", "week", "weeks", "month"])
        if has_fever and (is_prolonged or severity in ["moderate", "severe"]):
            red_flags_detected.append("Prolonged or severe febrile illness")
            return TriageDecision(
                urgency_level="CLINIC",
                urgency_label="Clinic: Visit Health Centre Within 24-48 Hours",
                color="#F59E0B",
                summary_reason="Fever lasting multiple days or causing significant discomfort needs to be evaluated for infection (such as malaria, pneumonia, or bacterial illness).",
                recommended_action="Visit your local clinic within 24 to 48 hours for a physical examination and diagnostic blood/malaria testing if appropriate. Stay well hydrated.",
                rule_fired="RULE-CL-02",
                red_flags=red_flags_detected,
                confidence=0.9
            )

        # RULE-CL-03: Inability to Bear Weight or Significant Joint/Bone Pain
        trauma_symptoms = ["fall", "injury", "swelling", "cannot walk", "cannot bear weight", "sprain", "twisted"]
        if any(k in str(answers).lower() or any(k in s for s in symptoms) for k in trauma_symptoms) and severity in ["moderate", "severe"]:
            red_flags_detected.append("Acute musculoskeletal trauma with functional impairment")
            return TriageDecision(
                urgency_level="CLINIC",
                urgency_label="Clinic: Visit Health Centre Within 24-48 Hours",
                color="#F59E0B",
                summary_reason="Difficulty bearing weight or severe swelling after an injury should be examined to rule out a fracture or ligament tear.",
                recommended_action="Keep the injured limb rested and elevated. Use a cold compress if available. Have it evaluated at a clinic within 1-2 days.",
                rule_fired="RULE-CL-03",
                red_flags=red_flags_detected,
                confidence=0.9
            )

        # RULE-CL-04: Persistent Productive Cough or Abdominal Pain
        cough_or_belly = ["cough", "productive cough", "yellow phlegm", "green phlegm", "stomach pain", "abdominal pain", "vomiting"]
        if any(any(k in s for s in symptoms) for k in cough_or_belly) and (is_prolonged or severity in ["moderate", "severe"]):
            red_flags_detected.append("Persistent respiratory or gastrointestinal symptoms")
            return TriageDecision(
                urgency_level="CLINIC",
                urgency_label="Clinic: Visit Health Centre Within 24-48 Hours",
                color="#F59E0B",
                summary_reason="Your ongoing cough or abdominal discomfort should be checked by a clinical officer or nurse to prevent worsening.",
                recommended_action="Schedule a visit to your local clinic in the next 1-2 days. Drink plenty of clean boiled water.",
                rule_fired="RULE-CL-04",
                red_flags=red_flags_detected,
                confidence=0.88
            )

        # ============================================================
        # 3. SELF-CARE / HOME MONITORING (Rule ID prefix: RULE-SC)
        # ============================================================
        if severity == "mild" and not red_flags_detected:
            return TriageDecision(
                urgency_level="SELF_CARE",
                urgency_label="Self-Care: Monitor at Home",
                color="#10B981",
                summary_reason="Your symptoms appear mild without danger signs. Most mild viral infections, minor strains, and headaches resolve with rest and home care.",
                recommended_action="Rest, drink plenty of fluids, and monitor how you feel. If your symptoms worsen, fever spikes, or new breathing difficulties develop, visit a clinic promptly.",
                rule_fired="RULE-SC-01",
                red_flags=[],
                confidence=0.85
            )

        # ============================================================
        # 4. SAFETY FAILSAFE (Rule ID: RULE-SAFETY-S3)
        # "When the session is ambiguous, default to the more urgent level"
        # ============================================================
        return TriageDecision(
            urgency_level="CLINIC",
            urgency_label="Clinic: Visit Health Centre Within 24-48 Hours",
            color="#F59E0B",
            summary_reason="To ensure your safety, an in-person clinical review is recommended because your symptoms require physical examination.",
            recommended_action="Have a healthcare worker check your symptoms at the nearest local clinic in the next 1 to 2 days.",
            rule_fired="RULE-SAFETY-S3",
            red_flags=["Ambiguous or moderate presentation defaulting to precautionary clinic review"],
            confidence=0.8
        )
