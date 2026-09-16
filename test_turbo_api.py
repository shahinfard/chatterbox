#!/usr/bin/env python3
"""
Quick test script for Chatterbox Turbo TTS API
"""
import time
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

import torch
from chatterbox.tts_turbo import ChatterboxTurboTTS

print("=" * 60)
print("Chatterbox Turbo TTS - Quick Test")
print("=" * 60)

# Detect device
device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"\nUsing device: {device}")

if device == "cuda":
    print(f"GPU: {torch.cuda.get_device_name(0)}")

# Load model
print("\nLoading Chatterbox Turbo model...")
start = time.time()
try:
    model = ChatterboxTurboTTS.from_pretrained(device=device)
    load_time = time.time() - start
    print(f"Model loaded in {load_time:.2f}s")
except Exception as e:
    print(f"ERROR loading model: {e}")
    sys.exit(1)

# Test text
test_text = "Hello! This is a test of the Chatterbox Turbo text-to-speech system."

# Check for voice sample
voice_sample = Path(__file__).parent / "david-attenborough.mp3"
if not voice_sample.exists():
    print(f"\nWARNING: Voice sample not found at {voice_sample}")
    print("Please ensure you have a voice sample file for testing.")
    print("\nGenerating with built-in voice (if available)...")
    use_voice = None
else:
    print(f"\nUsing voice sample: {voice_sample}")
    use_voice = str(voice_sample)

# Generate audio
print(f"\nGenerating: \"{test_text}\"")
gen_start = time.time()

try:
    if use_voice:
        wav = model.generate(test_text, audio_prompt_path=use_voice)
    else:
        wav = model.generate(test_text)
    
    gen_time = time.time() - gen_start
    audio_duration = wav.shape[-1] / model.sr
    rtf = gen_time / audio_duration if audio_duration > 0 else 0
    
    print(f"\nResults:")
    print(f"  Generation time: {gen_time:.3f}s")
    print(f"  Audio duration:  {audio_duration:.2f}s")
    print(f"  Real-time factor: {rtf:.3f}x")
    print(f"  Speed vs realtime: {1/rtf:.1f}x faster" if rtf > 0 else "")
    
    # Save output
    output_file = Path(__file__).parent / "test_turbo_output.wav"
    import torchaudio as ta
    ta.save(str(output_file), wav, model.sr)
    print(f"\nAudio saved to: {output_file}")
    
    print("\n" + "=" * 60)
    print("SUCCESS! Turbo model is working correctly.")
    print("=" * 60)
    
except Exception as e:
    print(f"\nERROR during generation: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
