"""Sister HTTP app: SAMPLE history with real Liquid extraction and fixed routing.
Synthetic demonstrations only; no validated clinical decisions or self-care clearance.
Legacy imaging endpoints remain available as unconfirmed attachments outside routing.
"""

import os
import io
import json
import base64
from typing import Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.sample_interview import SampleSessionManager as SessionManager, AUDIT_LOG_FILE, InterviewError, controller
from backend.imaging_analyzer import MedicalImageAnalyzer
from backend.liquid_engine import LiquidAIEngine

app = FastAPI(title="Sister - Offline Health Triage Assistant", version="1.0.0")

STATIC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "static"))
SAMPLES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "samples"))

# Mount static and samples directories
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
if os.path.exists(SAMPLES_DIR):
    app.mount("/samples", StaticFiles(directory=SAMPLES_DIR), name="samples")

class TurnRequest(BaseModel):
    session_id: str
    user_input: str = Field(min_length=1, max_length=8000)
    input_type: str = "text" # "text", "voice", "choice"
    voice_meta: Optional[dict] = None
    question_id: str
    revision: int
    turn_id: str = Field(min_length=1, max_length=100)
    choice_value: Optional[str] = None

class ActionRequest(BaseModel):
    session_id: str
    action: str
    field_id: Optional[str] = None

@app.exception_handler(InterviewError)
async def interview_error(request, exc):
    return JSONResponse(status_code=exc.status, content={"detail": str(exc)})

@app.post("/api/session/action")
def session_action(req: ActionRequest):
    return SessionManager.action(req.session_id, req.action, req.field_id)

@app.get("/api/session/{session_id}")
def session_state(session_id: str):
    return SessionManager.get_initial_prompt(session_id)


@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_file = os.path.join(STATIC_DIR, "sample.html")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h2>Sister backend running. Loading UI...</h2>")

@app.post("/api/session/start")
async def start_session():
    """
    Initializes a new patient triage session (F1, F2).
    """
    session = SessionManager.create_session()
    prompt = SessionManager.get_initial_prompt(session["session_id"])
    return JSONResponse({
        "session_id": session["session_id"],
        "prompt": prompt
    })

@app.post("/api/session/turn")
def handle_turn(req: TurnRequest):
    """
    Handles a single conversational turn in the interview (F1, F3, F4, F6).
    """
    resp = SessionManager.process_turn(
        session_id=req.session_id,
        user_input=req.user_input,
        input_type=req.input_type,
        voice_meta=req.voice_meta, question_id=req.question_id, revision=req.revision,
        turn_id=req.turn_id, choice_value=req.choice_value
    )
    return JSONResponse(resp)

@app.post("/api/transcribe")
def transcribe_audio(audio: UploadFile = File(...)):
    """
    Transcribes spoken answer from patient via LiquidAI/LFM3-Audio-2B (F12).
    """
    contents = audio.file.read(2_000_001)
    if len(contents) > 2_000_000:
        raise HTTPException(status_code=413, detail="Audio file too large")
    if not contents:
        raise HTTPException(status_code=400, detail="Empty audio file")
    
    result = LiquidAIEngine.transcribe_audio_wav(contents)
    return JSONResponse(result)

@app.post("/api/analyze-imaging")
async def analyze_imaging(
    session_id: str = Form(...),
    image: Optional[UploadFile] = File(None),
    image_base64: Optional[str] = Form(None)
):
    """
    Deep multimodal analysis of uploaded or webcam-captured X-Ray / MRI (F5, F9, F11).
    Pre-processes to 512x512 RGB for LiquidAI/LFM3-Omni-2B and detects clinical ROIs.
    """
    raw_bytes = None
    filename = "webcam_capture.jpg"
    
    if image is not None:
        raw_bytes = await image.read()
        filename = image.filename or "uploaded_scan.png"
    elif image_base64:
        if "," in image_base64:
            image_base64 = image_base64.split(",", 1)[1]
        raw_bytes = base64.b64decode(image_base64)
        filename = "camera_capture.jpg"
    else:
        raise HTTPException(status_code=400, detail="No image provided")

    session = SessionManager._require(session_id)
    if controller.value(session, "consent") != "yes":
        raise HTTPException(status_code=422, detail="Consent is required before image processing")
    # Legacy image analysis is stored separately and never changes SAMPLE routing.
    # Run deep radiological analysis
    analysis = MedicalImageAnalyzer.analyze(raw_bytes, filename)
    
    # Save a temporary copy of 512x512 preprocessed image for UI display
    processed_rel_path = f"/samples/{filename}"
    
    # Fold imaging findings into active session
    followup_resp = SessionManager.attach_imaging_analysis(session_id, analysis)
    
    return JSONResponse({
        "analysis": analysis,
        "session_response": followup_resp
    })

@app.get("/api/handover-note/{session_id}")
async def get_handover_note(session_id: str, format: str = "json"):
    """
    Returns the clinician handover note for the session (F8).
    """
    session = SessionManager.get_session(session_id)
    if not session or not session.get("handover_note"):
        raise HTTPException(status_code=404, detail="Session or handover note not found")
    
    note = session["handover_note"]
    if format == "text":
        return PlainTextResponse(content=note["raw_text"])
    return JSONResponse(note)

@app.get("/api/audit-log")
async def get_audit_log(limit: int = 50):
    """
    Retrieves flushed JSONL audit log entries for live inspection (F6).
    """
    entries = SessionManager.read_audit_log(limit=limit)
    return JSONResponse({"count": len(entries), "entries": entries})

@app.get("/api/samples")
async def list_samples():
    """
    Returns preset sample images for instant hackathon judge demonstration.
    """
    samples = [
        {
            "id": "cxr_normal",
            "name": "Normal Chest X-Ray",
            "modality": "X-Ray",
            "anatomy": "Chest",
            "file": "/samples/chest_xray_normal.png",
            "expected_outcome": "SELF_CARE (Clear lung fields, normal CTR)"
        },
        {
            "id": "cxr_pneumonia",
            "name": "Pneumonia Chest X-Ray (Focal Infiltrate)",
            "modality": "X-Ray",
            "anatomy": "Chest",
            "file": "/samples/chest_xray_pneumonia.png",
            "expected_outcome": "CLINIC (Right lung consolidation)"
        },
        {
            "id": "bone_fracture",
            "name": "Forearm Bone Fracture X-Ray",
            "modality": "X-Ray",
            "anatomy": "Bone / Extremity",
            "file": "/samples/bone_fracture_xray.png",
            "expected_outcome": "CLINIC (Cortical margin disruption / fracture)"
        },
        {
            "id": "brain_mri_normal",
            "name": "Normal Brain MRI (Axial T2)",
            "modality": "MRI",
            "anatomy": "Brain",
            "file": "/samples/brain_mri_normal.png",
            "expected_outcome": "SELF_CARE (Symmetric hemispheres, no mass effect)"
        },
        {
            "id": "brain_mri_stroke",
            "name": "Acute Ischemia / Lesion Brain MRI",
            "modality": "MRI",
            "anatomy": "Brain",
            "file": "/samples/brain_mri_acute_lesion.png",
            "expected_outcome": "CLINIC (Focal hemispheric signal abnormality)"
        }
    ]
    return JSONResponse(samples)

@app.get("/api/hardware-status")
async def get_hardware_status():
    """
    Telemetry and hardware status for offline judging demonstration (F7).
    """
    return JSONResponse({"runtime": LiquidAIEngine.runtime_status(),
                         "interview": "SAMPLE v0.1 — synthetic demo only",
                         "clinical_validation": False})
