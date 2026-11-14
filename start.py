#!/usr/bin/env python3
"""
start.py - Launcher for Sister Offline Health Triage & Imaging Assistant
Edge Native runtime for Dragonwing IQ-9075 / Local Workstation
"""

import os
import sys
import subprocess
import uvicorn

if __name__ == "__main__":
    host = os.environ.get("SISTER_HOST", "127.0.0.1")
    port = int(os.environ.get("SISTER_PORT", "8080"))

    print("=" * 70)
    print("  SISTER: SAMPLE history — synthetic demonstration only")
    print("  Host Target: Dragonwing IQ-9075 (Edge Native / Wi-Fi Cut Resilient)")
    print("  Audio: configured on-board Liquid package; confirm transcripts")
    print("  Vision Model: LiquidAI/LFM3-Omni-2B (512x512 Multimodal Vision)")
    print("  Interview: versioned SAMPLE questionnaire; no self-care clearance")
    print(f"  Access UI:   http://{host}:{port}")
    print("=" * 70)

    uvicorn.run("backend.main:app", host=host, port=port, log_level="info", reload=False)
