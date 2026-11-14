"""
test_direct_units.py - Comprehensive Unit & Pipeline Test Suite for Sister
Tests all modules directly without external HTTP or socket dependencies:
  1. LiquidAIEngine (Voice ASR LiquidAI/LFM3-Audio-2B & GenieX text reasoning)
  2. MedicalImageAnalyzer (Modality detection, CXR, Fracture X-Ray, Brain MRI)
  3. SessionManager (F1 conversation flow, F2 ingest, F6 flushed JSONL logging)
  4. ClinicalTriageEngine (Deterministic code rules RULE-EM, RULE-CL, RULE-SC)
  5. HandoverNoteGenerator (F8 structured clinical handover note)
"""

import os
import json
from backend.liquid_engine import LiquidAIEngine
from backend.imaging_analyzer import MedicalImageAnalyzer
from backend.session_manager import SessionManager, AUDIT_LOG_FILE
from backend.triage_rules import ClinicalTriageEngine, TriageDecision
from backend.handover_generator import HandoverNoteGenerator

def test_liquid_audio_engine():
    print("[1/5] Testing LiquidAI/LFM3-Audio-2B Speech Engine...")
    wav_path = "samples/sample_patient_answer.wav"
    with open(wav_path, "rb") as f:
        audio_bytes = f.read()

    res = LiquidAIEngine.transcribe_audio_wav(audio_bytes)
    print(f"  Transcript: \"{res['transcript']}\"")
    print(f"  Model: {res['model']} | Latency: {res['latency_ms']}ms | TTFT: {res['ttft_ms']}ms | Tok/s: {res['tokens_per_sec']}")
    assert res["model"] == "LiquidAI/LFM3-Audio-2B"
    assert res["latency_ms"] > 0
    print("  ✓ Liquid AI Audio Engine verified.")

def test_medical_imaging_xray_and_mri():
    print("\n[2/5] Testing Medical Imaging Pipeline (X-Ray & MRI)...")

    # A. Normal Chest X-Ray
    with open("samples/chest_xray_normal.png", "rb") as f:
        res = MedicalImageAnalyzer.analyze(f.read(), "chest_xray_normal.png")
        print(f"  A. Normal CXR: {res['scan_type']} -> {res['urgency_flag']}")
        print(f"     Observation: {res['primary_observation']}")
        assert res["modality"] == "X-RAY"
        assert res["anatomy"] == "Chest"
        assert res["urgency_flag"] == "SELF_CARE"

    # B. Pneumonia Chest X-Ray
    with open("samples/chest_xray_pneumonia.png", "rb") as f:
        res = MedicalImageAnalyzer.analyze(f.read(), "chest_xray_pneumonia.png")
        print(f"  B. Pneumonia CXR: {res['scan_type']} -> {res['urgency_flag']}")
        print(f"     Observation: {res['primary_observation']}")
        print(f"     ROIs detected: {len(res['rois'])}")
        assert res["urgency_flag"] == "CLINIC"
        assert len(res["rois"]) > 0

    # C. Bone Fracture X-Ray
    with open("samples/bone_fracture_xray.png", "rb") as f:
        res = MedicalImageAnalyzer.analyze(f.read(), "bone_fracture_xray.png")
        print(f"  C. Bone Fracture: {res['scan_type']} -> {res['urgency_flag']}")
        print(f"     Observation: {res['primary_observation']}")
        assert res["modality"] == "X-RAY"
        assert res["anatomy"] == "Bone / Extremity"
        assert res["urgency_flag"] == "CLINIC"

    # D. Brain MRI (Acute Focal Lesion)
    with open("samples/brain_mri_acute_lesion.png", "rb") as f:
        res = MedicalImageAnalyzer.analyze(f.read(), "brain_mri_acute_lesion.png")
        print(f"  D. Brain MRI (Lesion): {res['scan_type']} -> {res['urgency_flag']}")
        print(f"     Observation: {res['primary_observation']}")
        assert res["modality"] == "MRI"
        assert res["anatomy"] == "Brain"
        assert res["urgency_flag"] == "CLINIC"

    print("  ✓ All Medical Imaging modalities (X-Ray & MRI) verified.")

def test_full_consultation_flow():
    print("\n[3/5] Testing Conversational Flow & Ingestion (F1, F2, F5)...")
    session = SessionManager.create_session()
    sid = session["session_id"]
    print(f"  Created Session: {sid}")

    # Attach Chest X-Ray
    with open("samples/chest_xray_pneumonia.png", "rb") as f:
        analysis = MedicalImageAnalyzer.analyze(f.read(), "chest_xray_pneumonia.png")
    
    attach_resp = SessionManager.attach_imaging_analysis(sid, analysis)
    print(f"  Attached Imaging -> Sister Message: {attach_resp['sister_message'][:70]}...")
    assert "Chest Radiograph" in attach_resp["sister_message"]

    # Turn 1: Chief complaint
    t1 = SessionManager.process_turn(sid, "Cough and difficulty breathing with chills", "text")
    print(f"  Turn 1 -> Next Step: {t1['step']}")
    assert t1["step"] == "DURATION"

    # Turn 2: Duration
    t2 = SessionManager.process_turn(sid, "For 4 days", "text")
    print(f"  Turn 2 -> Next Step: {t2['step']}")
    assert t2["step"] == "SEVERITY"

    # Turn 3: Severity
    t3 = SessionManager.process_turn(sid, "Moderate fever and cough, no severe chest pain", "text")
    print(f"  Turn 3 -> Step: {t3['step']}")
    assert t3["step"] == "COMPLETE"
    assert t3["triage_decision"]["urgency_level"] == "CLINIC"
    print(f"  Triage Result: {t3['triage_decision']['urgency_label']}")
    print(f"  Rule Fired: {t3['triage_decision']['rule_fired']}")

    # Check Handover Note
    handover = t3["handover_note"]
    assert handover is not None
    assert sid in handover["session_id"]
    print("  ✓ Conversational triage flow verified.")

def test_deterministic_red_flags():
    print("\n[4/5] Testing Deterministic Red-Flag Rules (F4: Code Decides, Model Explains)...")

    # Test Rule 1: Emergency Chest Pain + Shortness of breath
    sess_emergency = {
        "symptoms": ["chest pain", "shortness of breath", "sweating"],
        "duration": "1 hour",
        "severity": "severe",
        "answers": {"radiation": "left arm"},
        "imaging_findings": None
    }
    dec_em = ClinicalTriageEngine.evaluate(sess_emergency)
    print(f"  Cardiac Emergency -> Level: {dec_em.urgency_level} | Rule: {dec_em.rule_fired}")
    assert dec_em.urgency_level == "EMERGENCY"
    assert dec_em.rule_fired == "RULE-EM-01"

    # Test Rule 2: FAST Stroke Signs
    sess_stroke = {
        "symptoms": ["sudden weakness", "slurred speech"],
        "duration": "30 minutes",
        "severity": "severe",
        "answers": {},
        "imaging_findings": None
    }
    dec_stroke = ClinicalTriageEngine.evaluate(sess_stroke)
    print(f"  Stroke Emergency  -> Level: {dec_stroke.urgency_level} | Rule: {dec_stroke.rule_fired}")
    assert dec_stroke.urgency_level == "EMERGENCY"
    assert dec_stroke.rule_fired == "RULE-EM-02"

    # Test Rule 3: Self-care mild cold
    sess_mild = {
        "symptoms": ["runny nose", "mild sneeze"],
        "duration": "1 day",
        "severity": "mild",
        "answers": {},
        "imaging_findings": None
    }
    dec_mild = ClinicalTriageEngine.evaluate(sess_mild)
    print(f"  Mild Self-Care    -> Level: {dec_mild.urgency_level} | Rule: {dec_mild.rule_fired}")
    assert dec_mild.urgency_level == "SELF_CARE"
    assert dec_mild.rule_fired == "RULE-SC-01"

    print("  ✓ Deterministic clinical rule engine verified.")

def test_audit_log_flushing():
    print("\n[5/5] Verifying Flushed JSONL Audit Log on Disk (F6)...")
    assert os.path.exists(AUDIT_LOG_FILE)
    entries = SessionManager.read_audit_log(limit=20)
    print(f"  Audit log contains {len(entries)} recent entries on disk ({AUDIT_LOG_FILE}).")
    assert len(entries) > 0
    latest = entries[-1]
    print(f"  Latest Log Line: timestamp={latest.get('timestamp')}, session_id={latest.get('session_id')}, step={latest.get('step')}")
    print("  ✓ JSONL audit log flushing verified.")

if __name__ == "__main__":
    print("=" * 60)
    print("  SISTER OFFLINE ASSISTANT - UNIT & PIPELINE TESTS")
    print("=" * 60)
    test_liquid_audio_engine()
    test_medical_imaging_xray_and_mri()
    test_full_consultation_flow()
    test_deterministic_red_flags()
    test_audit_log_flushing()
    print("\n" + "=" * 60)
    print("  🎉 ALL 5 PIPELINE MODULES PASSED SYSTEM VALIDATION!")
    print("=" * 60)
