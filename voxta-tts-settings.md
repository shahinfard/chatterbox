# Voxta TTS Settings for Chatterbox API

This document provides the correct settings for configuring Voxta to access the Chatterbox TTS OpenAI-compatible API.

## API Endpoint

**Request URL Template:**
```
http://192.168.1.225:5005/v1/audio/speech
```

Replace `192.168.1.225` with your server's IP address if different.

## Request Body

### Basic Configuration (Recommended - Non-Streaming)

```json
{
  "input": "{{ text }}",
  "voice": "her",
  "model": "tts-1",
  "response_format": "wav",
  "stream": false
}
```

**Note:** This is the tested and working configuration for Voxta. Streaming is not yet supported.

### Full Configuration (with optional parameters)

```json
{
  "input": "{{ text }}",
  "voice": "her",
  "model": "tts-1",
  "response_format": "wav",
  "stream": false,
  "speed": 1.0,
  "exaggeration": 0.5,
  "temperature": 0.8
}
```

## Available Voices

```json
{ "label": "Her", "parameters": { "voice": "her" } }
{ "label": "Alloy", "parameters": { "voice": "alloy" } }
{ "label": "Echo", "parameters": { "voice": "echo" } }
{ "label": "Fable", "parameters": { "voice": "fable" } }
{ "label": "Onyx", "parameters": { "voice": "onyx" } }
{ "label": "Nova", "parameters": { "voice": "nova" } }
{ "label": "Shimmer", "parameters": { "voice": "shimmer" } }
```

**Note:** All voices currently map to the `HER-sample1.wav` voice sample. You can customize this by modifying the `VOICE_PRESETS` mapping in `openai_api_server.py`.

## Parameter Reference

### Required Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `input` | string | The text to generate audio for (max 4096 characters) |

### Standard Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `voice` | string | `"her"` | Voice preset to use |
| `model` | string | `"tts-1"` | Model identifier (`tts-1` or `tts-1-hd`) |
| `response_format` | string | `"mp3"` | Audio format: `mp3`, `wav`, `opus`, `aac`, `flac`, `pcm` |
| `speed` | number | `1.0` | Playback speed (0.25 to 4.0) |
| `stream` | boolean | `false` | Enable streaming response |

### Advanced Parameters (Chatterbox-specific)

| Parameter | Type | Default | Range | Description |
|-----------|------|---------|-------|-------------|
| `exaggeration` | number | `0.5` | 0.0 - 1.0 | Emotion exaggeration level |
| `cfg_weight` | number | `0.5` | 0.0 - 5.0 | Classifier-free guidance weight |
| `temperature` | number | `0.8` | 0.1 - 2.0 | Sampling temperature for generation |

## Important Notes

1. **Numbers**: Use numeric values without quotes (e.g., `1.0`, not `"1.0"`)
2. **Booleans**: Use `true`/`false` without quotes (not `"true"`/`"false"`)
3. **Strings**: Use quotes for text values (e.g., `"her"`, `"mp3"`)
4. **JSON Syntax**: Remember commas between fields (except after the last field)
5. **Streaming**: When `stream: true`, audio chunks are returned progressively

## Example Configurations

### Low Latency (Streaming)
```json
{
  "input": "{{ text }}",
  "voice": "her",
  "model": "tts-1",
  "response_format": "mp3",
  "stream": true,
  "temperature": 0.7
}
```

### High Quality (Non-streaming)
```json
{
  "input": "{{ text }}",
  "voice": "her",
  "model": "tts-1-hd",
  "response_format": "flac",
  "stream": false,
  "exaggeration": 0.5,
  "temperature": 0.8
}
```

### Expressive Speech
```json
{
  "input": "{{ text }}",
  "voice": "her",
  "response_format": "wav",
  "stream": false,
  "exaggeration": 0.8,
  "temperature": 1.0
}
```

## Voxta Configuration UI Settings

When setting up Voxta HTTP API:

1. **Audio Content Type**: `audio/wav`
2. **Force Conversion**: `false`
3. **Request URL Template**: `http://192.168.1.225:5005/v1/audio/speech`
4. **Request Headers**: Leave empty (no headers needed)
5. **Request Content Type**: `application/json`
6. **Request Body**: Use one of the configurations above
7. **Manual Voices List**: Use the voices listed below

## Testing

You can test the API endpoint using curl:

```bash
curl -X POST http://192.168.1.225:5005/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{
    "input": "Hello, this is a test of the Chatterbox TTS API.",
    "voice": "her",
    "response_format": "wav",
    "stream": false
  }' \
  --output test_output.wav
```

Or check server health:

```bash
curl http://192.168.1.225:5005/health
```
