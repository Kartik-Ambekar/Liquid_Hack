"""
test_in_process.py - In-Process Verification Suite using Starlette/FastAPI TestClient
Runs 100% inside sandbox with zero external network or socket requirements.
"""

import os
import json
from starlette.testclient import TestClient
from backend.main import app

client = TestClient(app)

def test_hardware_status():
    resp = client.get("/api/hardware-status")
    assert resp.status_code == 200
    data = resp.json()
    print("✓ Hardware status:", data["platform"], "| Edge mode:", data["edge_mode"])
    assert data["platform"] == "Dragonwing IQ-9075"
    assert "LiquidAI/LFM3-Audio-2B" in data["models"]["audio"]

def test_samples_endpoint():
    resp = client.get("/api/samples")
    assert resp.status_code == 200
    data = resp.json()
    print(f"✓ Samples endpoint returned {len(data)} test presets.")
    assert len(data) >= 5

def test_full_patient_consultation_with_xray():
    # 1. Start Session
    resp = client.post("/api/session/start")
    assert resp.status_code == 200
    start_data = resp.json()
    session_id = start_data["session_id"]
    print(f"✓ Session started: {session_id}")

    # 2. Ingest Chest X-Ray with Pneumonia
    xray_path = "samples/chest_xray_pneumonia.png"
    with open(xray_path, "rb") as f:
        img_bytes = f.read()

    files = {"image": ("chest_xray_pneumonia.png", img_bytes, "image/png")}
    data = {"session_id": session_id}
    resp = client.post("/api/analyze-imaging", data=data, files=files)
    assert resp.status_code == 200
    img_res = resp.json()
    analysis = img_res["analysis"]
    print(f"✓ X-Ray Analyzed: {analysis['scan_type']}")
    print(f"  Primary Observation: {analysis['primary_observation']}")
    print(f"  ROIs Detected: {len(analysis['rois'])}")
    assert "opacity" in analysis["primary_observation"].lower() or "consolidation" in analysis["primary_observation"].lower()

    # 3. Patient answers symptom turn
    resp = client.post("/api/session/turn", json={
        "session_id": session_id,
        "user_input": "I have had a high fever and productive cough with green phlegm",
        "input_type": "text"
    })
    assert resp.status_code == 200
    turn1_res = resp.json()
    print(f"✓ Turn 1 (Chief Complaint) -> Next step: {turn1_res['step']}")

    # 4. Patient answers duration turn
    resp = client.post("/api/session/turn", json={
        "session_id": session_id,
        "user_input": "For about 4 days now",
        "input_type": "text"
    })
    assert resp.status_code == 200
    turn2_res = resp.json()
    print(f"✓ Turn 2 (Duration) -> Next step: {turn2_res['step']}")

    # 5. Patient answers severity turn -> Triggers deterministic triage
    resp = client.post("/api/session/turn", json={
        "session_id": session_id,
        "user_input": "Moderate, noticeable pain and chills but no severe breathing trouble",
        "input_type": "text"
    })
    assert resp.status_code == 200
    turn3_res = resp.json()
    decision = turn3_res.get("triage_decision")
    print(f"✓ Triage Complete! Urgency Level: {decision['urgency_level']} ({decision['urgency_label']})")
    print(f"  Rule Fired: {decision['rule_fired']}")
    print(f"  Reason: {decision['summary_reason']}")
    assert decision["urgency_level"] in ["CLINIC", "EMERGENCY"]
    assert turn3_res["handover_note"] is not None

    # 6. Verify Handover Note
    resp = client.get(f"/api/handover-note/{session_id}?format=text")
    assert resp.status_code == 200
    handover_text = resp.text
    print("✓ Handover Note retrieved successfully:")
    print("--------------------------------------------------")
    print(handover_text[:350] + "...\n[Full note truncated for test log]")
    print("--------------------------------------------------")
    assert "SISTER OFFLINE CLINICAL HANDOVER NOTE" in handover_text
    assert session_id in handover_text

def test_brain_mri_analysis():
    session_id = "SIST-TESTMRI"
    mri_path = "samples/brain_mri_acute_lesion.png"
    with open(mri_path, "rb") as f:
        img_bytes = f.read()

    files = {"image": ("brain_mri_acute_lesion.png", img_bytes, "image/png")}
    data = {"session_id": session_id}
    resp = client.post("/api/analyze-imaging", data=data, files=files)
    assert resp.status_code == 200
    img_res = resp.json()
    analysis = img_res["analysis"]
    print(f"✓ Brain MRI Analyzed: {analysis['scan_type']}")
    print(f"  Primary Observation: {analysis['primary_observation']}")
    assert analysis["modality"] == "MRI"
    assert analysis["anatomy"] == "Brain"

def test_audio_transcription():
    wav_path = "samples/sample_patient_answer.wav"
    with open(wav_path, "rb") as f:
        audio_bytes = f.read()

    files = {"audio": ("sample_patient_answer.wav", audio_bytes, "audio/wav")}
    resp = client.post("/api/transcribe", files=files)
    assert resp.status_code == 200
    res = resp.json()
    print(f"✓ Audio Transcribed: \"{res['transcript']}\"")
    print(f"  ASR Model: {res['model']} | Latency: {res['latency_ms']}ms | TTFT: {res['ttft_ms']}ms")
    assert res["model"] == "LiquidAI/LFM3-Audio-2B"

def test_flushed_audit_log():
    resp = client.get("/api/audit-log")
    assert resp.status_code == 200
    data = resp.json()
    print(f"✓ Audit Log Verified: {data['count']} flushed JSONL entries on disk.")
    assert data["count"] > 0
    latest = data["entries"][-1]
    print(f"  Latest log event: {latest.get('event') or latest.get('step')} | Timestamp: {latest.get('timestamp')}")

if __name__ == "__main__":
    print("\nRunning In-Process Verification Suite for Sister...")
    test_hardware_status()
    test_samples_endpoint()
    test_full_patient_consultation_with_xray()
    test_brain_mri_analysis()
    test_audio_transcription()
    test_flushed_audit_log()
    print("\n🎉 ALL TESTS PASSED! SISTER SYSTEM FULLY OPERATIONAL AND VERIFIED.\n")
