# Chatterbox TTS - OpenAI Compatible API Server

This API server wraps Chatterbox TTS with an OpenAI-compatible `/v1/audio/speech` endpoint, making it easy to integrate with tools like OpenWebUI.

## Features

- **OpenAI TTS API Compatible** - Drop-in replacement for OpenAI's TTS API
- **Voice Cloning** - Uses your custom voice samples (HER-sample1.wav/mp3)
- **Streaming Support** - Real-time audio streaming with low latency
- **Multiple Audio Formats** - MP3, WAV, OPUS, AAC, FLAC, PCM
- **High Quality** - Powered by Chatterbox TTS with voice cloning
- **Fast Inference** - Sub-realtime generation (RTF < 0.5 on GPU)

## Installation

### 1. Install Base Chatterbox Requirements

```bash
# Install base Chatterbox dependencies
pip install -e .
```

### 2. Install API Server Requirements

```bash
# Install FastAPI and related dependencies
pip install -r api_requirements.txt
```

### 3. Verify Voice Samples

Make sure your voice sample files are in the root directory:
- `HER-sample1.wav`
- `HER-sample1.mp3` (optional alternative)

## Usage

### Starting the Server

```bash
# Run the API server
python openai_api_server.py
```

The server will start on `http://0.0.0.0:8000` by default.

**On first run**, the server will automatically download the Chatterbox models from HuggingFace (~2GB). This may take a few minutes.

### Server Endpoints

- **POST** `/v1/audio/speech` - Generate speech (OpenAI compatible)
- **GET** `/` - Server info
- **GET** `/health` - Health check

### Configuration

Edit the `ServerConfig` class in `openai_api_server.py` to customize:

```python
class ServerConfig:
    HOST = "0.0.0.0"           # Server host
    PORT = 8000                # Server port
    MODEL_DEVICE = "cuda"      # "cuda", "mps", or "cpu"

    # Voice presets mapping
    VOICE_PRESETS = {
        "her": "HER-sample1.wav",
        "alloy": "HER-sample1.wav",  # Add your own samples here
        ...
    }

    # TTS generation parameters
    DEFAULT_EXAGGERATION = 0.5      # Emotion control (0.0-1.0)
    DEFAULT_CFG_WEIGHT = 0.5        # Guidance strength
    DEFAULT_TEMPERATURE = 0.8       # Sampling randomness
```

## API Usage

### Basic Request (cURL)

```bash
curl http://localhost:8000/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{
    "model": "tts-1",
    "input": "Hello! This is a test of the Chatterbox TTS system with voice cloning.",
    "voice": "her",
    "response_format": "mp3"
  }' \
  --output speech.mp3
```

### Streaming Request

```bash
curl http://localhost:8000/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{
    "model": "tts-1",
    "input": "This will stream audio in real-time as it generates.",
    "voice": "her",
    "stream": true
  }' \
  --output speech.mp3
```

### Python Client

```python
import requests

# Non-streaming
response = requests.post(
    "http://localhost:8000/v1/audio/speech",
    json={
        "model": "tts-1",
        "input": "Hello from Python!",
        "voice": "her",
        "response_format": "mp3"
    }
)

with open("output.mp3", "wb") as f:
    f.write(response.content)

# Streaming
response = requests.post(
    "http://localhost:8000/v1/audio/speech",
    json={
        "model": "tts-1",
        "input": "Streaming audio generation!",
        "voice": "her",
        "stream": True
    },
    stream=True
)

with open("output_stream.mp3", "wb") as f:
    for chunk in response.iter_content(chunk_size=8192):
        f.write(chunk)
```

### OpenAI Python Library

```python
from openai import OpenAI

# Point to local server
client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="not-needed"  # API key not required for local server
)

# Generate speech
response = client.audio.speech.create(
    model="tts-1",
    voice="her",
    input="Hello! This works with the OpenAI Python library!"
)

response.stream_to_file("output.mp3")
```

## OpenWebUI Integration

### 1. Configure OpenWebUI

In OpenWebUI settings:

1. Go to **Settings** → **Audio**
2. Set **TTS Engine** to **OpenAI**
3. Set **API Base URL** to `http://localhost:8000/v1`
4. Set **API Key** to anything (not required)
5. Select **Voice** as `her`

### 2. Test in OpenWebUI

Type a message and click the speaker icon to hear it spoken with your cloned voice!

## API Request Schema

### Request Body

```json
{
  "model": "tts-1",                    // Required: "tts-1" or "tts-1-hd"
  "input": "Text to speak",            // Required: Text (max 4096 chars)
  "voice": "her",                      // Required: Voice preset name
  "response_format": "mp3",            // Optional: mp3, wav, opus, aac, flac, pcm
  "speed": 1.0,                        // Optional: 0.25 to 4.0 (currently unused)
  "stream": false,                     // Optional: Enable streaming

  // Extended Chatterbox parameters (optional)
  "exaggeration": 0.5,                 // Emotion intensity (0.0-1.0)
  "cfg_weight": 0.5,                   // Guidance weight (0.0-5.0)
  "temperature": 0.8                   // Sampling temperature (0.1-2.0)
}
```

### Response

**Non-streaming**: Returns audio file directly

**Streaming**: Returns chunked audio data with `Transfer-Encoding: chunked`

## Available Voices

Current voice presets (all use HER-sample1.wav):
- `her` - Your custom voice
- `alloy` - OpenAI compatibility (uses HER voice)
- `echo` - OpenAI compatibility (uses HER voice)
- `fable` - OpenAI compatibility (uses HER voice)
- `onyx` - OpenAI compatibility (uses HER voice)
- `nova` - OpenAI compatibility (uses HER voice)
- `shimmer` - OpenAI compatibility (uses HER voice)

### Adding More Voices

1. Add your voice sample files to the root directory (e.g., `john-voice.wav`)
2. Update `VOICE_PRESETS` in `ServerConfig`:

```python
VOICE_PRESETS = {
    "her": "HER-sample1.wav",
    "john": "john-voice.wav",
    "mary": "mary-voice.mp3",
}
```

3. Restart the server
4. Use the new voice: `"voice": "john"`

## Audio Formats

Supported output formats:
- **mp3** - MP3 audio (default, best compatibility)
- **wav** - WAV audio (uncompressed)
- **opus** - Opus codec (efficient streaming)
- **aac** - AAC audio
- **flac** - FLAC lossless
- **pcm** - Raw PCM 16-bit

## Performance

**GPU (NVIDIA 4090):**
- First chunk latency: ~0.47s
- Real-time factor (RTF): ~0.50
- Streaming: Yes, real-time capable

**CPU:**
- Slower generation (RTF > 1.0)
- Streaming still supported
- May not achieve real-time

**Apple Silicon (MPS):**
- Good performance
- Set `MODEL_DEVICE = "mps"`

## Troubleshooting

### Model Download Issues

If model download fails:
```bash
# Pre-download models
python -c "from src.chatterbox.tts import ChatterboxTTS; ChatterboxTTS.from_pretrained()"
```

### Voice Sample Not Found

```
FileNotFoundError: Voice sample not found: HER-sample1.wav
```

**Solution:** Ensure voice files are in the root directory where `openai_api_server.py` is located.

### CUDA Out of Memory

**Solution:**
- Reduce `DEFAULT_CHUNK_SIZE` in config (e.g., to 15)
- Use CPU: `MODEL_DEVICE = "cpu"`

### Import Errors

```
ModuleNotFoundError: No module named 'chatterbox'
```

**Solution:**
```bash
pip install -e .
```

## Advanced Configuration

### Running on Different Port

```bash
# Edit openai_api_server.py
class ServerConfig:
    PORT = 5000  # Change to your desired port
```

### Environment Variables

Set these before starting:
```bash
export CUDA_VISIBLE_DEVICES=0  # Use specific GPU
python openai_api_server.py
```

### Production Deployment

For production, use a process manager:

```bash
# Install gunicorn
pip install gunicorn

# Run with gunicorn (single worker recommended due to model size)
gunicorn openai_api_server:app \
  --workers 1 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --timeout 120
```

### Reverse Proxy (Nginx)

```nginx
server {
    listen 80;
    server_name tts.yourdomain.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_buffering off;  # Important for streaming
    }
}
```

## Development

### Testing the API

```bash
# Health check
curl http://localhost:8000/health

# Test generation
curl http://localhost:8000/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{"model":"tts-1","input":"Test","voice":"her"}' \
  -o test.mp3

# Play the result
ffplay test.mp3  # or your preferred audio player
```

### Logs

Server logs include:
- Request details (voice, format, text length)
- Generation metrics (latency, RTF, duration)
- Errors and warnings

### API Documentation

Once running, visit:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## License

This API server follows the same license as Chatterbox TTS.

## Credits

- **Chatterbox TTS**: https://github.com/resemble-ai/chatterbox
- **Streaming Fork**: Original repository this is based on
- **FastAPI**: https://fastapi.tiangolo.com/

## Support

For issues specific to:
- **API Server**: Check logs and this README
- **Chatterbox TTS**: See main Chatterbox documentation
- **OpenWebUI**: Check OpenWebUI documentation

Happy voice cloning!
