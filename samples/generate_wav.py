"""
generate_wav.py - Creates a standard 16kHz 16-bit Mono WAV fixture for Sister
Compatible with LiquidAI/LFM3-Audio-2B and Dragonwing IQ-9075 ASR specs.
"""

import os
import wave
import struct
import math

WAV_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "sample_patient_answer.wav"))

def generate_sample_wav():
    sample_rate = 16000
    duration_sec = 2.5 # ~2.5 seconds
    num_samples = int(sample_rate * duration_sec)
    
    with wave.open(WAV_PATH, 'wb') as wf:
        wf.setnchannels(1) # Mono
        wf.setsampwidth(2) # 16-bit
        wf.setframerate(sample_rate)
        
        # Synthesize a speech-like acoustic envelope
        frames = bytearray()
        for i in range(num_samples):
            t = i / sample_rate
            # Multi-frequency formant modulation
            mod = 0.5 * (1 + math.sin(2 * math.pi * 3 * t))
            val = (
                0.4 * math.sin(2 * math.pi * 180 * t) +
                0.3 * math.sin(2 * math.pi * 720 * t) +
                0.2 * math.sin(2 * math.pi * 2100 * t)
            ) * mod
            int_val = int(max(-32767, min(32767, val * 24000)))
            frames.extend(struct.pack('<h', int_val))
            
        wf.writeframes(frames)
    print(f"Generated sample WAV at {WAV_PATH}")

if __name__ == "__main__":
    generate_sample_wav()
