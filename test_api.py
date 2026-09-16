"""
Test script for Chatterbox TTS OpenAI API Server

Usage:
    python test_api.py
"""

import requests
import time
from pathlib import Path

# Configuration
API_BASE_URL = "http://localhost:5005"
OUTPUT_DIR = Path("api_test_outputs")

# Ensure output directory exists
OUTPUT_DIR.mkdir(exist_ok=True)


def test_health_check():
    """Test health check endpoint"""
    print("\n" + "="*60)
    print("TEST 1: Health Check")
    print("="*60)

    try:
        response = requests.get(f"{API_BASE_URL}/health")
        response.raise_for_status()
        data = response.json()

        print(f"Status: {data['status']}")
        print(f"Model Loaded: {data['model_loaded']}")
        print(f"Device: {data['device']}")
        print("✓ Health check passed")
        return True
    except Exception as e:
        print(f"✗ Health check failed: {e}")
        return False


def test_basic_generation():
    """Test basic non-streaming generation"""
    print("\n" + "="*60)
    print("TEST 2: Basic TTS Generation (Non-Streaming)")
    print("="*60)

    try:
        text = "Hello! This is a test of the Chatterbox TTS API with voice cloning."
        print(f"Input text: {text}")

        start_time = time.time()

        response = requests.post(
            f"{API_BASE_URL}/v1/audio/speech",
            json={
                "model": "tts-1",
                "input": text,
                "voice": "her",
                "response_format": "mp3"
            }
        )
        response.raise_for_status()

        elapsed = time.time() - start_time

        # Save audio
        output_file = OUTPUT_DIR / "test_basic.mp3"
        with open(output_file, "wb") as f:
            f.write(response.content)

        file_size = len(response.content)
        print(f"Generated in: {elapsed:.2f}s")
        print(f"Output size: {file_size:,} bytes")
        print(f"Saved to: {output_file}")
        print("✓ Basic generation passed")
        return True
    except Exception as e:
        print(f"✗ Basic generation failed: {e}")
        return False


def test_streaming_generation():
    """Test streaming generation"""
    print("\n" + "="*60)
    print("TEST 3: Streaming TTS Generation")
    print("="*60)

    try:
        text = "This is a streaming test. The audio should be generated and delivered in real-time chunks."
        print(f"Input text: {text}")

        start_time = time.time()
        first_chunk_time = None
        chunk_count = 0
        total_bytes = 0

        response = requests.post(
            f"{API_BASE_URL}/v1/audio/speech",
            json={
                "model": "tts-1",
                "input": text,
                "voice": "her",
                "response_format": "mp3",
                "stream": True
            },
            stream=True
        )
        response.raise_for_status()

        # Save streaming output
        output_file = OUTPUT_DIR / "test_streaming.mp3"
        with open(output_file, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    if first_chunk_time is None:
                        first_chunk_time = time.time()
                    chunk_count += 1
                    total_bytes += len(chunk)
                    f.write(chunk)

        elapsed = time.time() - start_time
        latency = first_chunk_time - start_time if first_chunk_time else 0

        print(f"First chunk latency: {latency:.2f}s")
        print(f"Total time: {elapsed:.2f}s")
        print(f"Chunks received: {chunk_count}")
        print(f"Total size: {total_bytes:,} bytes")
        print(f"Saved to: {output_file}")
        print("✓ Streaming generation passed")
        return True
    except Exception as e:
        print(f"✗ Streaming generation failed: {e}")
        return False


def test_different_formats():
    """Test different audio formats"""
    print("\n" + "="*60)
    print("TEST 4: Multiple Audio Formats")
    print("="*60)

    formats = ["mp3", "wav", "opus", "flac"]
    text = "Testing audio format conversion."
    results = []

    for fmt in formats:
        try:
            print(f"\nTesting format: {fmt}")
            response = requests.post(
                f"{API_BASE_URL}/v1/audio/speech",
                json={
                    "model": "tts-1",
                    "input": text,
                    "voice": "her",
                    "response_format": fmt
                }
            )
            response.raise_for_status()

            output_file = OUTPUT_DIR / f"test_format.{fmt}"
            with open(output_file, "wb") as f:
                f.write(response.content)

            file_size = len(response.content)
            print(f"  ✓ {fmt}: {file_size:,} bytes -> {output_file}")
            results.append(True)
        except Exception as e:
            print(f"  ✗ {fmt} failed: {e}")
            results.append(False)

    success_count = sum(results)
    print(f"\nFormats working: {success_count}/{len(formats)}")
    return all(results)


def test_extended_parameters():
    """Test Chatterbox-specific parameters"""
    print("\n" + "="*60)
    print("TEST 5: Extended Parameters (Exaggeration, CFG, Temp)")
    print("="*60)

    test_configs = [
        {"name": "neutral", "exaggeration": 0.0, "cfg_weight": 0.5, "temperature": 0.8},
        {"name": "expressive", "exaggeration": 1.0, "cfg_weight": 0.5, "temperature": 0.8},
        {"name": "creative", "exaggeration": 0.5, "cfg_weight": 0.3, "temperature": 1.2},
    ]

    text = "This tests different emotional and creative parameters."
    results = []

    for config in test_configs:
        try:
            name = config.pop("name")
            print(f"\nTesting: {name} - {config}")

            response = requests.post(
                f"{API_BASE_URL}/v1/audio/speech",
                json={
                    "model": "tts-1",
                    "input": text,
                    "voice": "her",
                    "response_format": "mp3",
                    **config
                }
            )
            response.raise_for_status()

            output_file = OUTPUT_DIR / f"test_params_{name}.mp3"
            with open(output_file, "wb") as f:
                f.write(response.content)

            print(f"  ✓ {name}: Saved to {output_file}")
            results.append(True)
        except Exception as e:
            print(f"  ✗ {name} failed: {e}")
            results.append(False)

    success_count = sum(results)
    print(f"\nConfigurations working: {success_count}/{len(test_configs)}")
    return all(results)


def test_openai_library_compatibility():
    """Test with OpenAI Python library (if installed)"""
    print("\n" + "="*60)
    print("TEST 6: OpenAI Library Compatibility")
    print("="*60)

    try:
        from openai import OpenAI
    except ImportError:
        print("OpenAI library not installed - skipping this test")
        print("Install with: pip install openai")
        return None

    try:
        client = OpenAI(
            base_url=f"{API_BASE_URL}/v1",
            api_key="not-needed"
        )

        response = client.audio.speech.create(
            model="tts-1",
            voice="her",
            input="Testing with the official OpenAI Python library!"
        )

        output_file = OUTPUT_DIR / "test_openai_lib.mp3"
        response.stream_to_file(str(output_file))

        print(f"✓ OpenAI library test passed")
        print(f"Saved to: {output_file}")
        return True
    except Exception as e:
        print(f"✗ OpenAI library test failed: {e}")
        return False


def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("CHATTERBOX TTS API TEST SUITE")
    print("="*60)
    print(f"API URL: {API_BASE_URL}")
    print(f"Output directory: {OUTPUT_DIR}")

    # Check if server is running
    try:
        requests.get(f"{API_BASE_URL}/health", timeout=2)
    except requests.exceptions.RequestException:
        print("\n✗ ERROR: API server is not running!")
        print("Please start the server first: python openai_api_server.py")
        return

    # Run tests
    results = {
        "Health Check": test_health_check(),
        "Basic Generation": test_basic_generation(),
        "Streaming Generation": test_streaming_generation(),
        "Audio Formats": test_different_formats(),
        "Extended Parameters": test_extended_parameters(),
        "OpenAI Library": test_openai_library_compatibility(),
    }

    # Print summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)

    passed = 0
    failed = 0
    skipped = 0

    for test_name, result in results.items():
        if result is True:
            status = "✓ PASSED"
            passed += 1
        elif result is False:
            status = "✗ FAILED"
            failed += 1
        else:
            status = "⊘ SKIPPED"
            skipped += 1

        print(f"{test_name:.<40} {status}")

    print(f"\nTotal: {passed} passed, {failed} failed, {skipped} skipped")

    if failed == 0:
        print("\n🎉 All tests passed! The API is working correctly.")
        print(f"\nGenerated audio files are in: {OUTPUT_DIR}/")
        print("You can play them to verify audio quality.")
    else:
        print("\n⚠ Some tests failed. Check the output above for details.")


if __name__ == "__main__":
    main()
