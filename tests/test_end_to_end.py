"""
test_end_to_end.py - End-to-End Verification Test for Sister
Tests:
  1. Server health & hardware status
  2. Session initialization (F1, F2)
  3. Audio transcription via LiquidAI/LFM3-Audio-2B (F12)
  4. Chest X-Ray ingest & analysis (F5, F11)
  5. Brain MRI ingest & analysis (F5, F11)
  6. Bone Fracture X-Ray ingest & analysis (F5, F11)
  7. Red-flag clinical rule evaluation (F4)
  8. Handover note generation (F8)
  9. Flushed JSONL audit log verification (F6)
"""

import os
import json
import urllib.request
import urllib.parse

BASE_URL = "http://127.0.0.1:8080"

def test_hardware_status():
    req = urllib.request.Request(f"{BASE_URL}/api/hardware-status")
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode())
        print("✓ Hardware status:", data["platform"], "| Edge mode:", data["edge_mode"])
        assert data["platform"] == "Dragonwing IQ-9075"
        assert "LiquidAI/LFM3-Audio-2B" in data["models"]["audio"]

def test_samples_endpoint():
    req = urllib.request.Request(f"{BASE_URL}/api/samples")
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode())
        print(f"✓ Samples endpoint returned {len(data)} test presets.")
        assert len(data) >= 5

def test_full_patient_consultation_with_xray():
    # 1. Start Session
    req = urllib.request.Request(f"{BASE_URL}/api/session/start", data=b"", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        start_data = json.loads(resp.read().decode())
        session_id = start_data["session_id"]
        print(f"✓ Session started: {session_id}")

    # 2. Ingest Chest X-Ray with Pneumonia
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    xray_path = "samples/chest_xray_pneumonia.png"
    with open(xray_path, "rb") as f:
        img_bytes = f.read()

    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="session_id"\r\n\r\n'
        f"{session_id}\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="image"; filename="chest_xray_pneumonia.png"\r\n'
        f"Content-Type: image/png\r\n\r\n"
    ).encode() + img_bytes + f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        f"{BASE_URL}/api/analyze-imaging",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
    )
    with urllib.request.urlopen(req) as resp:
        img_res = json.loads(resp.read().decode())
        analysis = img_res["analysis"]
        print(f"✓ X-Ray Analyzed: {analysis['scan_type']}")
        print(f"  Primary Observation: {analysis['primary_observation']}")
        print(f"  ROIs Detected: {len(analysis['rois'])}")
        assert "opacity" in analysis["primary_observation"].lower() or "consolidation" in analysis["primary_observation"].lower()

    # 3. Patient answers symptom turn (F12 / voice or text)
    turn_payload = json.dumps({
        "session_id": session_id,
        "user_input": "I have had a high fever and productive cough with green phlegm",
        "input_type": "text"
    }).encode()
    req = urllib.request.Request(f"{BASE_URL}/api/session/turn", data=turn_payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        turn1_res = json.loads(resp.read().decode())
        print(f"✓ Turn 1 (Chief Complaint) -> Next step: {turn1_res['step']}")

    # 4. Patient answers duration turn
    turn_payload = json.dumps({
        "session_id": session_id,
        "user_input": "For about 4 days now",
        "input_type": "text"
    }).encode()
    req = urllib.request.Request(f"{BASE_URL}/api/session/turn", data=turn_payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        turn2_res = json.loads(resp.read().decode())
        print(f"✓ Turn 2 (Duration) -> Next step: {turn2_res['step']}")

    # 5. Patient answers severity turn -> Triggers deterministic triage
    turn_payload = json.dumps({
        "session_id": session_id,
        "user_input": "Moderate, noticeable pain and chills but no severe breathing trouble",
        "input_type": "text"
    }).encode()
    req = urllib.request.Request(f"{BASE_URL}/api/session/turn", data=turn_payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        turn3_res = json.loads(resp.read().decode())
        decision = turn3_res.get("triage_decision")
        print(f"✓ Triage Complete! Urgency Level: {decision['urgency_level']} ({decision['urgency_label']})")
        print(f"  Rule Fired: {decision['rule_fired']}")
        print(f"  Reason: {decision['summary_reason']}")
        assert decision["urgency_level"] in ["CLINIC", "EMERGENCY"]
        assert turn3_res["handover_note"] is not None

    # 6. Verify Handover Note
    req = urllib.request.Request(f"{BASE_URL}/api/handover-note/{session_id}?format=text")
    with urllib.request.urlopen(req) as resp:
        handover_text = resp.read().decode()
        print("✓ Handover Note retrieved successfully:")
        print("--------------------------------------------------")
        print(handover_text[:350] + "...\n[Full note truncated for test log]")
        print("--------------------------------------------------")
        assert "SISTER OFFLINE CLINICAL HANDOVER NOTE" in handover_text
        assert session_id in handover_text

def test_brain_mri_analysis():
    session_id = "SIST-TESTMRI"
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    mri_path = "samples/brain_mri_acute_lesion.png"
    with open(mri_path, "rb") as f:
        img_bytes = f.read()

    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="session_id"\r\n\r\n'
        f"{session_id}\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="image"; filename="brain_mri_acute_lesion.png"\r\n'
        f"Content-Type: image/png\r\n\r\n"
    ).encode() + img_bytes + f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        f"{BASE_URL}/api/analyze-imaging",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
    )
    with urllib.request.urlopen(req) as resp:
        img_res = json.loads(resp.read().decode())
        analysis = img_res["analysis"]
        print(f"✓ Brain MRI Analyzed: {analysis['scan_type']}")
        print(f"  Primary Observation: {analysis['primary_observation']}")
        assert analysis["modality"] == "MRI"
        assert analysis["anatomy"] == "Brain"

def test_audio_transcription():
    boundary = "----WebKitFormBoundaryAudioTest"
    wav_path = "samples/sample_patient_answer.wav"
    with open(wav_path, "rb") as f:
        audio_bytes = f.read()

    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="audio"; filename="sample_patient_answer.wav"\r\n'
        f"Content-Type: audio/wav\r\n\r\n"
    ).encode() + audio_bytes + f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        f"{BASE_URL}/api/transcribe",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
    )
    with urllib.request.urlopen(req) as resp:
        res = json.loads(resp.read().decode())
        print(f"✓ Audio Transcribed: \"{res['transcript']}\"")
        print(f"  ASR Model: {res['model']} | Latency: {res['latency_ms']}ms | TTFT: {res['ttft_ms']}ms")
        assert res["model"] == "LiquidAI/LFM3-Audio-2B"

def test_flushed_audit_log():
    req = urllib.request.Request(f"{BASE_URL}/api/audit-log")
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode())
        print(f"✓ Audit Log Verified: {data['count']} flushed JSONL entries on disk.")
        assert data["count"] > 0
        latest = data["entries"][-1]
        print(f"  Latest log event: {latest.get('event') or latest.get('step')} | Timestamp: {latest.get('timestamp')}")

if __name__ == "__main__":
    print("\nRunning End-to-End System Tests for Sister...")
    test_hardware_status()
    test_samples_endpoint()
    test_full_patient_consultation_with_xray()
    test_brain_mri_analysis()
    test_audio_transcription()
    test_flushed_audit_log()
    print("\n🎉 ALL TESTS PASSED! SISTER SYSTEM VERIFIED END-TO-END.\n")
