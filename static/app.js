/**
 * Sister - Offline Health Triage & Medical Imaging Assistant
 * Client-Side Controller (app.js)
 * 100% Offline Edge Native.
 */

// Global State
let currentSessionId = null;
let isRecording = false;
let audioContext = null;
let mediaStream = null;
let audioRecorder = null;
let recordedAudioChunks = [];
let recordingTimer = null;
let recordingSeconds = 0;
let voiceOutputEnabled = true;
let currentImagingAnalysis = null;
let currentImageBitmap = null;
let showBoundingBoxes = true;
let cameraStream = null;

// DOM Elements
const messagesContainer = document.getElementById("messages-container");
const quickChoicesContainer = document.getElementById("quick-choices-container");
const sessionBadge = document.getElementById("session-badge");
const btnNewSession = document.getElementById("btn-new-session");
const btnRecordVoice = document.getElementById("btn-record-voice");
const recordLabel = document.getElementById("record-label");
const textInputForm = document.getElementById("text-input-form");
const textInput = document.getElementById("text-input");
const btnToggleSpeech = document.getElementById("btn-toggle-speech");
const speechIcon = document.getElementById("speech-icon");

// Feedback Box
const transcriptFeedback = document.getElementById("transcript-feedback");
const transcriptText = document.getElementById("transcript-text");
const asrMetrics = document.getElementById("asr-metrics");
const btnConfirmTranscript = document.getElementById("btn-confirm-transcript");
const btnRerecordTranscript = document.getElementById("btn-rerecord-transcript");

// Tabs
const tabImagingBtn = document.getElementById("tab-imaging-btn");
const tabHandoverBtn = document.getElementById("tab-handover-btn");
const tabSamplesBtn = document.getElementById("tab-samples-btn");
const tabImaging = document.getElementById("tab-imaging");
const tabHandover = document.getElementById("tab-handover");
const tabSamples = document.getElementById("tab-samples");

// Imaging
const dropZone = document.getElementById("drop-zone");
const scanFileInput = document.getElementById("scan-file-input");
const btnOpenCamera = document.getElementById("btn-open-camera");
const imageViewerContainer = document.getElementById("image-viewer-container");
const imagingCanvas = document.getElementById("imaging-canvas");
const scanMetaTag = document.getElementById("scan-meta-tag");
const btnToggleBoxes = document.getElementById("btn-toggle-boxes");
const imagingAnalysisCard = document.getElementById("imaging-analysis-card");
const analysisUrgencyBadge = document.getElementById("analysis-urgency-badge");
const analysisPrimaryObs = document.getElementById("analysis-primary-obs");
const analysisMetricsGrid = document.getElementById("analysis-metrics-grid");

// Handover
const handoverContent = document.getElementById("handover-content");
const btnCopyHandover = document.getElementById("btn-copy-handover");
const btnPrintHandover = document.getElementById("btn-print-handover");

// Samples & Audit
const samplesList = document.getElementById("samples-list");
const btnShowAudit = document.getElementById("btn-show-audit");
const auditModal = document.getElementById("audit-modal");
const btnCloseAudit = document.getElementById("btn-close-audit");
const btnRefreshAudit = document.getElementById("btn-refresh-audit");
const auditLogPre = document.getElementById("audit-log-pre");

// Camera Modal
const cameraModal = document.getElementById("camera-modal");
const cameraVideo = document.getElementById("camera-video");
const btnCaptureFrame = document.getElementById("btn-capture-frame");
const btnCloseCamera = document.getElementById("btn-close-camera");
const btnCancelCamera = document.getElementById("btn-cancel-camera");

// Initialization
document.addEventListener("DOMContentLoaded", () => {
  setupEventListeners();
  startNewSession();
  loadSamplePresets();
});

function setupEventListeners() {
  btnNewSession.addEventListener("click", startNewSession);
  textInputForm.addEventListener("submit", handleTextSubmit);
  
  // Voice controls
  btnRecordVoice.addEventListener("click", toggleVoiceRecording);
  btnConfirmTranscript.addEventListener("click", sendConfirmedTranscript);
  btnRerecordTranscript.addEventListener("click", rerecordVoice);
  btnToggleSpeech.addEventListener("click", toggleSpeechSynthesis);

  // Tabs
  tabImagingBtn.addEventListener("click", () => switchTab("imaging"));
  tabHandoverBtn.addEventListener("click", () => switchTab("handover"));
  tabSamplesBtn.addEventListener("click", () => switchTab("samples"));

  // Imaging
  dropZone.addEventListener("click", () => scanFileInput.click());
  dropZone.addEventListener("dragover", (e) => { e.preventDefault(); dropZone.classList.add("dragover"); });
  dropZone.addEventListener("dragleave", () => dropZone.classList.remove("dragover"));
  dropZone.addEventListener("drop", handleFileDrop);
  scanFileInput.addEventListener("change", handleFileSelect);
  btnToggleBoxes.addEventListener("click", toggleBoundingBoxes);

  // Camera
  btnOpenCamera.addEventListener("click", openCameraModal);
  btnCloseCamera.addEventListener("click", closeCameraModal);
  btnCancelCamera.addEventListener("click", closeCameraModal);
  btnCaptureFrame.addEventListener("click", captureCameraFrame);

  // Handover actions
  btnCopyHandover.addEventListener("click", copyHandoverText);
  btnPrintHandover.addEventListener("click", printHandoverNote);

  // Audit modal
  btnShowAudit.addEventListener("click", openAuditModal);
  btnCloseAudit.addEventListener("click", () => auditModal.classList.add("hidden"));
  btnRefreshAudit.addEventListener("click", loadAuditLog);
}

function switchTab(tabName) {
  [tabImagingBtn, tabHandoverBtn, tabSamplesBtn].forEach(b => b.classList.remove("active"));
  [tabImaging, tabHandover, tabSamples].forEach(c => c.classList.remove("active"));

  if (tabName === "imaging") {
    tabImagingBtn.classList.add("active");
    tabImaging.classList.add("active");
  } else if (tabName === "handover") {
    tabHandoverBtn.classList.add("active");
    tabHandover.classList.add("active");
  } else if (tabName === "samples") {
    tabSamplesBtn.classList.add("active");
    tabSamples.classList.add("active");
  }
}

// Session Management
async function startNewSession() {
  messagesContainer.innerHTML = "";
  quickChoicesContainer.innerHTML = "";
  transcriptFeedback.classList.add("hidden");
  imagingAnalysisCard.classList.add("hidden");
  imageViewerContainer.classList.add("hidden");
  handoverContent.innerHTML = `<div class="placeholder-text">Complete the interview session to generate the structured handover note.</div>`;
  currentImagingAnalysis = null;
  currentImageBitmap = null;

  try {
    const res = await fetch("/api/session/start", { method: "POST" });
    const data = await res.json();
    currentSessionId = data.session_id;
    sessionBadge.textContent = `Session: ${currentSessionId}`;
    
    appendSisterMessage(data.prompt.sister_message);
    renderChoices(data.prompt.choices);
    speakAloud(data.prompt.spoken_text);
  } catch (err) {
    console.error("Session start error:", err);
    appendSisterMessage("Welcome. Unable to reach edge backend. Please ensure the server is active.");
  }
}

async function sendTurn(userInput, inputType = "text", voiceMeta = null) {
  if (!userInput.trim()) return;

  // Append user bubble
  appendUserMessage(userInput);
  quickChoicesContainer.innerHTML = "";
  transcriptFeedback.classList.add("hidden");

  // Show thinking indicator
  const thinkingId = appendSisterThinking();

  try {
    const res = await fetch("/api/session/turn", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: currentSessionId,
        user_input: userInput,
        input_type: inputType,
        voice_meta: voiceMeta
      })
    });
    const data = await res.json();
    removeThinking(thinkingId);

    // If completed with triage decision
    if (data.triage_decision) {
      appendSisterMessage(data.sister_message, data.triage_decision);
      renderHandoverNote(data.handover_note);
      switchTab("handover");
    } else {
      appendSisterMessage(data.sister_message);
    }

    renderChoices(data.choices || []);
    speakAloud(data.spoken_text);

  } catch (err) {
    removeThinking(thinkingId);
    appendSisterMessage("Encountered an edge processing error. Please retry or visit a health clinic.");
  }
}

function handleTextSubmit(e) {
  e.preventDefault();
  const text = textInput.value.trim();
  if (text) {
    sendTurn(text, "text");
    textInput.value = "";
  }
}

function renderChoices(choices) {
  quickChoicesContainer.innerHTML = "";
  if (!choices || choices.length === 0) return;

  choices.forEach(ch => {
    const btn = document.createElement("button");
    btn.className = "choice-chip";
    btn.textContent = ch.label;
    btn.addEventListener("click", () => {
      if (ch.action === "open_ingest" || ch.action === "open_upload") {
        switchTab("imaging");
        scanFileInput.click();
      } else if (ch.action === "open_camera") {
        openCameraModal();
      } else if (ch.action === "download_handover") {
        printHandoverNote();
      } else if (ch.action === "new_session") {
        startNewSession();
      } else {
        sendTurn(ch.label, "choice");
      }
    });
    quickChoicesContainer.appendChild(btn);
  });
}

// Message Rendering
function appendSisterMessage(text, triageDecision = null) {
  const bubble = document.createElement("div");
  bubble.className = "message-bubble sister";

  let innerHtml = `
    <div class="avatar">🩺</div>
    <div class="bubble-content">
      <div>${formatMarkdown(text)}</div>
  `;

  if (triageDecision) {
    const levelClass = triageDecision.urgency_level.toLowerCase();
    innerHtml += `
      <div class="triage-result-card ${levelClass}">
        <div class="triage-title" style="color:${triageDecision.color}">
          <span>🚨</span> ${triageDecision.urgency_label}
        </div>
        <p><strong>Clinical Reason:</strong> ${triageDecision.summary_reason}</p>
        <p style="margin-top:6px;"><strong>Next Steps:</strong> ${triageDecision.recommended_action}</p>
        <div class="bubble-meta">Deterministic Rule: <code>${triageDecision.rule_fired}</code> | Failsafe: Active</div>
      </div>
    `;
  }

  innerHtml += `
      <div class="bubble-meta">
        <span>Sister (Dragonwing IQ-9075)</span>
        <span>•</span>
        <span>${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
      </div>
    </div>
  `;

  bubble.innerHTML = innerHtml;
  messagesContainer.appendChild(bubble);
  messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

function appendUserMessage(text) {
  const bubble = document.createElement("div");
  bubble.className = "message-bubble patient";
  bubble.innerHTML = `
    <div class="avatar">👤</div>
    <div class="bubble-content">
      <div>${escapeHtml(text)}</div>
      <div class="bubble-meta" style="justify-content: flex-end; color: rgba(255,255,255,0.7);">
        <span>Patient Response</span>
      </div>
    </div>
  `;
  messagesContainer.appendChild(bubble);
  messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

function appendSisterThinking() {
  const id = "thinking-" + Date.now();
  const bubble = document.createElement("div");
  bubble.id = id;
  bubble.className = "message-bubble sister";
  bubble.innerHTML = `
    <div class="avatar">🩺</div>
    <div class="bubble-content" style="display:flex; align-items:center; gap:8px;">
      <span class="dot-green"></span>
      <span class="text-sm text-muted">Sister is reasoning locally...</span>
    </div>
  `;
  messagesContainer.appendChild(bubble);
  messagesContainer.scrollTop = messagesContainer.scrollHeight;
  return id;
}

function removeThinking(id) {
  const el = document.getElementById(id);
  if (el) el.remove();
}

// Voice Recording Pipeline (F12)
async function toggleVoiceRecording() {
  if (isRecording) {
    stopVoiceRecording();
  } else {
    startVoiceRecording();
  }
}

async function startVoiceRecording() {
  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
    
    const source = audioContext.createMediaStreamSource(mediaStream);
    const processor = audioContext.createScriptProcessor(4096, 1, 1);
    
    recordedAudioChunks = [];
    processor.onaudioprocess = (e) => {
      const inputData = e.inputBuffer.getChannelData(0);
      recordedAudioChunks.push(new Float32Array(inputData));
    };

    source.connect(processor);
    processor.connect(audioContext.destination);

    audioRecorder = { source, processor };
    isRecording = true;
    recordingSeconds = 0;

    btnRecordVoice.classList.add("recording");
    recordLabel.textContent = "Listening... (0s)";

    recordingTimer = setInterval(() => {
      recordingSeconds++;
      recordLabel.textContent = `Listening... (${recordingSeconds}s / 30s)`;
      if (recordingSeconds >= 30) {
        stopVoiceRecording();
      }
    }, 1000);

  } catch (err) {
    console.error("Mic access failed:", err);
    alert("Microphone access unavailable. You can use the text box below.");
  }
}

async function stopVoiceRecording() {
  if (!isRecording) return;
  clearInterval(recordingTimer);
  isRecording = false;

  btnRecordVoice.classList.remove("recording");
  recordLabel.textContent = "Transcribing...";

  if (audioRecorder) {
    audioRecorder.processor.disconnect();
    audioRecorder.source.disconnect();
  }
  if (mediaStream) {
    mediaStream.getTracks().forEach(t => t.stop());
  }

  // Encode to 16kHz 16-bit Mono PCM WAV
  const wavBlob = encodeWAV(recordedAudioChunks, 16000);
  await uploadAudioForTranscription(wavBlob);
  recordLabel.textContent = "Hold to Speak";
}

function encodeWAV(samplesArrays, sampleRate) {
  let totalLength = samplesArrays.reduce((acc, arr) => acc + arr.length, 0);
  let merged = new Float32Array(totalLength);
  let offset = 0;
  for (let arr of samplesArrays) {
    merged.set(arr, offset);
    offset += arr.length;
  }

  const buffer = new ArrayBuffer(44 + merged.length * 2);
  const view = new DataView(buffer);

  // RIFF header
  writeString(view, 0, 'RIFF');
  view.setUint32(4, 36 + merged.length * 2, true);
  writeString(view, 8, 'WAVE');
  writeString(view, 12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); // PCM format
  view.setUint16(22, 1, true); // Mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true); // Byte rate
  view.setUint16(32, 2, true); // Block align
  view.setUint16(34, 16, true); // Bits per sample
  writeString(view, 36, 'data');
  view.setUint32(40, merged.length * 2, true);

  // PCM samples
  let index = 44;
  for (let i = 0; i < merged.length; i++) {
    let s = Math.max(-1, Math.min(1, merged[i]));
    view.setInt16(index, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
    index += 2;
  }

  return new Blob([view], { type: 'audio/wav' });
}

function writeString(view, offset, string) {
  for (let i = 0; i < string.length; i++) {
    view.setUint8(offset + i, string.charCodeAt(i));
  }
}

async function uploadAudioForTranscription(wavBlob) {
  const formData = new FormData();
  formData.append("audio", wavBlob, "voice_input.wav");

  try {
    const res = await fetch("/api/transcribe", { method: "POST", body: formData });
    const data = await res.json();

    transcriptText.textContent = data.transcript;
    asrMetrics.textContent = `LiquidAI/LFM3-Audio-2B • Latency: ${data.latency_ms}ms • TTFT: ${data.ttft_ms}ms`;
    transcriptFeedback.classList.remove("hidden");
  } catch (err) {
    console.error("ASR error:", err);
    transcriptText.textContent = "Could not transcribe audio. Please type your answer.";
    transcriptFeedback.classList.remove("hidden");
  }
}

function sendConfirmedTranscript() {
  const text = transcriptText.textContent.trim();
  if (text) {
    sendTurn(text, "voice", { asr_model: "LiquidAI/LFM3-Audio-2B" });
  }
}

function rerecordVoice() {
  transcriptFeedback.classList.add("hidden");
  toggleVoiceRecording();
}

// Speech Synthesis Read Aloud (F16)
function speakAloud(text) {
  if (!voiceOutputEnabled || !('speechSynthesis' in window) || !text) return;
  window.speechSynthesis.cancel();
  const clean = text.replace(/[*_#]/g, '');
  const utterance = new SpeechSynthesisUtterance(clean);
  utterance.rate = 0.95;
  utterance.pitch = 1.05;
  window.speechSynthesis.speak(utterance);
}

function toggleSpeechSynthesis() {
  voiceOutputEnabled = !voiceOutputEnabled;
  if (!voiceOutputEnabled) {
    window.speechSynthesis.cancel();
    speechIcon.textContent = "🔇";
    btnToggleSpeech.classList.add("text-muted");
  } else {
    speechIcon.textContent = "🔊";
    btnToggleSpeech.classList.remove("text-muted");
  }
}

// Medical Imaging & X-Ray/MRI Pipeline (F5, F9, F11)
function handleFileDrop(e) {
  e.preventDefault();
  dropZone.classList.remove("dragover");
  if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
    processImageFile(e.dataTransfer.files[0]);
  }
}

function handleFileSelect(e) {
  if (e.target.files && e.target.files.length > 0) {
    processImageFile(e.target.files[0]);
  }
}

async function processImageFile(file) {
  switchTab("imaging");
  scanMetaTag.textContent = `Analyzing ${file.name}...`;
  imageViewerContainer.classList.remove("hidden");

  // Render on canvas
  const reader = new FileReader();
  reader.onload = async (e) => {
    const img = new Image();
    img.onload = () => {
      currentImageBitmap = img;
      renderImageOnCanvas();
    };
    img.src = e.target.result;

    // Send to backend
    const formData = new FormData();
    formData.append("session_id", currentSessionId);
    formData.append("image", file);
    await submitImagingData(formData);
  };
  reader.readAsDataURL(file);
}

async function submitImagingData(formData) {
  try {
    const res = await fetch("/api/analyze-imaging", { method: "POST", body: formData });
    const data = await res.json();
    currentImagingAnalysis = data.analysis;

    // Update UI elements
    scanMetaTag.textContent = `${data.analysis.scan_type} • 512×512 RGB (LFM3-Omni-2B)`;
    renderImagingAnalysisCard(data.analysis);
    renderImageOnCanvas();

    // Update chat with folded observation (F5)
    appendSisterMessage(data.session_response.sister_message);
    renderChoices(data.session_response.choices);
    speakAloud(data.session_response.spoken_text);

  } catch (err) {
    console.error("Imaging analysis error:", err);
    scanMetaTag.textContent = "Error analyzing scan";
  }
}

function renderImageOnCanvas() {
  if (!currentImageBitmap) return;
  const ctx = imagingCanvas.getContext("2d");
  ctx.clearRect(0, 0, 512, 512);

  // Fill black background
  ctx.fillStyle = "#000000";
  ctx.fillRect(0, 0, 512, 512);

  // Draw preprocessed image
  ctx.drawImage(currentImageBitmap, 0, 0, 512, 512);

  // Draw Bounding Boxes (F11)
  if (showBoundingBoxes && currentImagingAnalysis && currentImagingAnalysis.rois) {
    currentImagingAnalysis.rois.forEach(roi => {
      const [ymin, xmin, ymax, xmax] = roi.box_2d;
      const w = xmax - xmin;
      const h = ymax - ymin;

      ctx.strokeStyle = roi.color || "#38BDF8";
      ctx.lineWidth = 2.5;
      ctx.strokeRect(xmin, ymin, w, h);

      // Label badge
      ctx.fillStyle = roi.color || "#38BDF8";
      ctx.fillRect(xmin, Math.max(0, ymin - 22), ctx.measureText(roi.label).width + 16, 20);

      ctx.fillStyle = "#0F172A";
      ctx.font = "bold 11px -apple-system, sans-serif";
      ctx.fillText(roi.label, xmin + 6, Math.max(14, ymin - 8));
    });
  }
}

function toggleBoundingBoxes() {
  showBoundingBoxes = !showBoundingBoxes;
  btnToggleBoxes.textContent = showBoundingBoxes ? "Hide Bounding Boxes" : "Show Bounding Boxes";
  renderImageOnCanvas();
}

function renderImagingAnalysisCard(analysis) {
  imagingAnalysisCard.classList.remove("hidden");

  // Badge
  analysisUrgencyBadge.textContent = analysis.urgency_flag;
  analysisUrgencyBadge.className = `badge ${analysis.urgency_flag.toLowerCase()}`;

  // Primary observation
  analysisPrimaryObs.textContent = analysis.primary_observation;

  // Metrics grid
  analysisMetricsGrid.innerHTML = "";
  if (analysis.metrics) {
    for (const [k, v] of Object.entries(analysis.metrics)) {
      const div = document.createElement("div");
      div.className = "metric-item";
      div.innerHTML = `
        <div class="metric-label">${k.replace(/_/g, ' ').toUpperCase()}</div>
        <div class="metric-val">${v}</div>
      `;
      analysisMetricsGrid.appendChild(div);
    }
  }
}

// Camera Capture (F9)
async function openCameraModal() {
  cameraModal.classList.remove("hidden");
  try {
    cameraStream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "environment", width: { ideal: 1280 }, height: { ideal: 720 } }
    });
    cameraVideo.srcObject = cameraStream;
  } catch (err) {
    console.error("Camera access failed:", err);
    alert("Camera unavailable on this browser or permissions denied.");
    closeCameraModal();
  }
}

function closeCameraModal() {
  cameraModal.classList.add("hidden");
  if (cameraStream) {
    cameraStream.getTracks().forEach(t => t.stop());
    cameraStream = null;
  }
}

async function captureCameraFrame() {
  if (!cameraVideo) return;
  const tempCanvas = document.createElement("canvas");
  tempCanvas.width = 512;
  tempCanvas.height = 512;
  const ctx = tempCanvas.getContext("2d");

  // Crop square center
  const minDim = Math.min(cameraVideo.videoWidth, cameraVideo.videoHeight);
  const startX = (cameraVideo.videoWidth - minDim) / 2;
  const startY = (cameraVideo.videoHeight - minDim) / 2;
  ctx.drawImage(cameraVideo, startX, startY, minDim, minDim, 0, 0, 512, 512);

  const base64Data = tempCanvas.toDataURL("image/jpeg", 0.92);
  closeCameraModal();

  // Display on main canvas
  const img = new Image();
  img.onload = () => {
    currentImageBitmap = img;
    renderImageOnCanvas();
  };
  img.src = base64Data;
  switchTab("imaging");
  imageViewerContainer.classList.remove("hidden");
  scanMetaTag.textContent = "Analyzing Camera Scan Frame...";

  // Submit to backend
  const formData = new FormData();
  formData.append("session_id", currentSessionId);
  formData.append("image_base64", base64Data);
  await submitImagingData(formData);
}

// Handover Note (F8)
function renderHandoverNote(note) {
  if (!note) return;
  handoverContent.textContent = note.raw_text;
}

function copyHandoverText() {
  const text = handoverContent.textContent;
  if (!text || text.includes("Complete the interview")) return;
  navigator.clipboard.writeText(text);
  btnCopyHandover.textContent = "✅ Copied!";
  setTimeout(() => btnCopyHandover.textContent = "📋 Copy Text", 2000);
}

function printHandoverNote() {
  const text = handoverContent.textContent;
  if (!text || text.includes("Complete the interview")) return;
  const printWindow = window.open("", "_blank");
  printWindow.document.write(`
    <html>
      <head>
        <title>Sister Clinical Handover Note</title>
        <style>
          body { font-family: monospace; padding: 24px; font-size: 13px; line-height: 1.5; white-space: pre-wrap; }
        </style>
      </head>
      <body>${escapeHtml(text)}</body>
    </html>
  `);
  printWindow.document.close();
  printWindow.focus();
  setTimeout(() => { printWindow.print(); }, 250);
}

// Preset Samples (Judge Testing)
async function loadSamplePresets() {
  try {
    const res = await fetch("/api/samples");
    const samples = await res.json();
    samplesList.innerHTML = "";

    samples.forEach(s => {
      const card = document.createElement("div");
      card.className = "sample-card";
      card.innerHTML = `
        <div class="sample-info">
          <h4>${s.name}</h4>
          <p>${s.modality} • Expected: <strong>${s.expected_outcome}</strong></p>
        </div>
        <button class="primary-btn btn-sm">Load Preset</button>
      `;
      card.addEventListener("click", () => loadSampleImage(s));
      samplesList.appendChild(card);
    });
  } catch (err) {
    console.error("Samples load error:", err);
  }
}

async function loadSampleImage(sample) {
  switchTab("imaging");
  scanMetaTag.textContent = `Loading ${sample.name}...`;
  imageViewerContainer.classList.remove("hidden");

  const img = new Image();
  img.crossOrigin = "anonymous";
  img.onload = async () => {
    currentImageBitmap = img;
    renderImageOnCanvas();

    // Fetch blob and send
    const blobRes = await fetch(sample.file);
    const blob = await blobRes.blob();
    const formData = new FormData();
    formData.append("session_id", currentSessionId);
    formData.append("image", blob, sample.file.split("/").pop());
    await submitImagingData(formData);
  };
  img.src = sample.file;
}

// Audit Log Modal (F6)
async function openAuditModal() {
  auditModal.classList.remove("hidden");
  await loadAuditLog();
}

async function loadAuditLog() {
  auditLogPre.textContent = "Loading flushed JSONL records...";
  try {
    const res = await fetch("/api/audit-log?limit=40");
    const data = await res.json();
    if (!data.entries || data.entries.length === 0) {
      auditLogPre.textContent = "No audit log entries found. Start a consultation turn to record logs.";
      return;
    }
    auditLogPre.textContent = data.entries.map(e => JSON.stringify(e, null, 2)).join("\n\n");
  } catch (err) {
    auditLogPre.textContent = "Error loading audit records: " + err.message;
  }
}

// Utility Helpers
function formatMarkdown(text) {
  if (!text) return "";
  let html = escapeHtml(text);
  // Bold
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  // Italic
  html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');
  // Newlines
  html = html.replace(/\n\n/g, '<br><br>').replace(/\n/g, '<br>');
  return html;
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}
