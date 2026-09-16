# Quick Start Guide - Chatterbox TTS OpenAI API

Your OpenAI-compatible TTS API is now ready to use with your custom HER voice!

## Server Status

**Server is currently running on:** `http://localhost:5005`

The server automatically uses your voice samples:
- `HER-sample1.wav`
- `HER-sample1.mp3`

## Quick Test

The API is already tested and working! Check these generated test files:
- `test_output.mp3` - Non-streaming generation
- `test_streaming.mp3` - Streaming generation

## Using with OpenWebUI

### 1. Configure OpenWebUI

1. Open OpenWebUI and go to **Settings**
2. Navigate to **Audio** settings
3. Configure as follows:
   - **TTS Engine:** OpenAI
   - **API Base URL:** `http://localhost:5005/v1`
   - **API Key:** `anything` (not validated)
   - **Voice:** `her`
   - **Model:** `tts-1`

### 2. Test in OpenWebUI

Type any message and click the speaker icon - you should hear it in your HER voice!

## Basic Usage Examples

### Using cURL

```bash
# Generate speech
curl -X POST http://localhost:5005/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{"model":"tts-1","input":"Hello from your custom voice!","voice":"her"}' \
  -o output.mp3

# With streaming
curl -X POST http://localhost:5005/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{"model":"tts-1","input":"Streaming test","voice":"her","stream":true}' \
  -o output.mp3
```

### Using Python

```python
import requests

response = requests.post(
    "http://localhost:5005/v1/audio/speech",
    json={
        "model": "tts-1",
        "input": "Hello from Python!",
        "voice": "her"
    }
)

with open("output.mp3", "wb") as f:
    f.write(response.content)
```

### Using OpenAI Python Library

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:5005/v1",
    api_key="not-needed"
)

response = client.audio.speech.create(
    model="tts-1",
    voice="her",
    input="Hello from OpenAI library!"
)

response.stream_to_file("output.mp3")
```

## Starting the Server

### Current Session
The server is currently running in the background.

### Future Sessions

**Windows:**
```bash
python openai_api_server.py
# or double-click: start_api_server.bat
```

**Linux/Mac:**
```bash
python openai_api_server.py
# or: bash start_api_server.sh
```

## Available Endpoints

- **POST** `/v1/audio/speech` - Generate speech (OpenAI compatible)
- **GET** `/health` - Health check
- **GET** `/` - Server info
- **GET** `/docs` - Interactive API documentation

Visit http://localhost:5005/docs for interactive Swagger UI!

## Configuration

Edit `openai_api_server.py` to customize:

```python
class ServerConfig:
    PORT = 5005              # Your firewall-approved port
    MODEL_DEVICE = "cuda"    # "cuda", "mps", or "cpu"

    # Voice presets
    VOICE_PRESETS = {
        "her": "HER-sample1.wav",
        # Add more voices here
    }
```

## Performance

**Your Current Setup:**
- Device: CUDA (GPU acceleration)
- First chunk latency: ~1.3s (streaming)
- Real-time factor: ~1.2 (streaming)

## Supported Audio Formats

- **mp3** (default, best compatibility)
- **wav** (uncompressed)
- **opus** (efficient streaming)
- **aac** (AAC audio)
- **flac** (lossless)
- **pcm** (raw audio)

Example with different format:
```bash
curl -X POST http://localhost:5005/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{"model":"tts-1","input":"Test","voice":"her","response_format":"wav"}' \
  -o output.wav
```

## Advanced Parameters

Chatterbox-specific controls:

```json
{
  "model": "tts-1",
  "input": "Your text here",
  "voice": "her",
  "exaggeration": 0.5,    // Emotion intensity (0.0-1.0)
  "cfg_weight": 0.5,      // Guidance strength (0.0-5.0)
  "temperature": 0.8,     // Creativity (0.1-2.0)
  "stream": true          // Enable streaming
}
```

## Troubleshooting

### Server Not Responding
Check if server is running:
```bash
curl http://localhost:5005/health
```

### Voice Quality Issues
- Try adjusting `exaggeration` (0.0 = neutral, 1.0 = expressive)
- Adjust `cfg_weight` (lower = more creative, higher = more controlled)
- Adjust `temperature` (lower = consistent, higher = varied)

### Port Already in Use
Edit `openai_api_server.py` and change `PORT = 5005` to another port.

## Adding More Voices

1. Place new voice sample files (WAV/MP3) in the repo root
2. Edit `openai_api_server.py`:
```python
VOICE_PRESETS = {
    "her": "HER-sample1.wav",
    "alex": "alex-voice.wav",
    "morgan": "morgan-voice.mp3",
}
```
3. Restart the server
4. Use new voice: `"voice": "alex"`

## Full Documentation

See `API_SERVER_README.md` for complete documentation.

## Testing

Run the full test suite:
```bash
python test_api.py
```

This will test all features and generate sample audio files in `api_test_outputs/`.

---

**Server is ready!** Access it at `http://localhost:5005` 🎉
