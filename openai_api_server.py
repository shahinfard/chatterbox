"""
OpenAI-compatible TTS API server for Chatterbox
Implements /v1/audio/speech endpoint compatible with OpenAI's TTS API
"""

import io
import logging
import os
import sys
import subprocess
from pathlib import Path
from typing import Literal, Optional, Generator
import time

import torch
import torchaudio
import soundfile as sf
import numpy as np
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel, Field, validator
import uvicorn

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from chatterbox.tts import ChatterboxTTS

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# Configuration
# ============================================================================

class ServerConfig:
    """Server configuration"""
    HOST = "0.0.0.0"
    PORT = 5005
    MODEL_DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

    # Voice samples directory
    VOICE_SAMPLES_DIR = Path(__file__).parent

    # Voice presets mapping
    VOICE_PRESETS = {
        "her": "HER-sample1.wav",
        "laura": "laura-voice.wav",
        "emilia": "emilia-clarke-tts-file.wav",
        "david": "david-attenborough.wav",
        "morgan": "morgan-freeman.wav",   # Fallback to HER
        "nova": "HER-sample1.wav",   # Fallback to HER
        "shimmer": "HER-sample1.wav" # Fallback to HER
    }

    # TTS generation defaults
    DEFAULT_EXAGGERATION = 0.5
    DEFAULT_CFG_WEIGHT = 0.5
    DEFAULT_TEMPERATURE = 0.8
    DEFAULT_CHUNK_SIZE = 25
    DEFAULT_CONTEXT_WINDOW = 50
    DEFAULT_FADE_DURATION = 0.02

    # Audio output settings
    SAMPLE_RATE = 24000  # S3GEN_SR from Chatterbox


# ============================================================================
# Request/Response Models
# ============================================================================

class TTSRequest(BaseModel):
    """OpenAI TTS API request model"""
    model: str = Field(
        default="tts-1",
        description="Model to use (tts-1 or tts-1-hd)"
    )
    input: str = Field(
        ...,
        description="The text to generate audio for. Maximum length is 4096 characters.",
        max_length=4096
    )
    voice: str = Field(
        default="her",
        description="Voice preset to use"
    )
    response_format: Literal["mp3", "opus", "aac", "flac", "wav", "pcm"] = Field(
        default="mp3",
        description="Audio format for response"
    )
    speed: float = Field(
        default=1.0,
        description="Speed of generated audio (0.25 to 4.0)",
        ge=0.25,
        le=4.0
    )

    # Extended parameters for Chatterbox-specific control
    exaggeration: Optional[float] = Field(
        default=None,
        description="Emotion exaggeration (0.0 to 1.0)",
        ge=0.0,
        le=1.0
    )
    cfg_weight: Optional[float] = Field(
        default=None,
        description="Classifier-free guidance weight",
        ge=0.0,
        le=5.0
    )
    temperature: Optional[float] = Field(
        default=None,
        description="Sampling temperature",
        ge=0.1,
        le=2.0
    )
    stream: bool = Field(
        default=False,
        description="Whether to stream audio chunks"
    )

    @validator('voice')
    def validate_voice(cls, v):
        v_lower = v.lower()
        if v_lower not in ServerConfig.VOICE_PRESETS:
            logger.warning(f"Unknown voice '{v}', defaulting to 'her'")
            return "her"
        return v_lower


# ============================================================================
# Global Model Instance
# ============================================================================

class ModelManager:
    """Manages the TTS model instance"""
    def __init__(self):
        self.model: Optional[ChatterboxTTS] = None
        self.device = ServerConfig.MODEL_DEVICE

    def load_model(self):
        """Load the Chatterbox TTS model"""
        if self.model is None:
            logger.info(f"Loading Chatterbox TTS model on device: {self.device}")
            try:
                self.model = ChatterboxTTS.from_pretrained(device=self.device)
                logger.info("Model loaded successfully")
            except Exception as e:
                logger.error(f"Failed to load model: {e}")
                raise
        return self.model

    def get_voice_path(self, voice_name: str) -> Path:
        """Get the path to voice sample file"""
        voice_file = ServerConfig.VOICE_PRESETS.get(voice_name, "HER-sample1.wav")
        voice_path = ServerConfig.VOICE_SAMPLES_DIR / voice_file

        if not voice_path.exists():
            logger.warning(f"Voice file not found: {voice_path}")
            # Try alternative extensions
            for ext in [".mp3", ".wav", ".flac"]:
                alt_path = voice_path.with_suffix(ext)
                if alt_path.exists():
                    logger.info(f"Using alternative voice file: {alt_path}")
                    return alt_path
            raise FileNotFoundError(f"Voice sample not found: {voice_path}")

        return voice_path


model_manager = ModelManager()


# ============================================================================
# Audio Processing Utilities
# ============================================================================

def convert_audio_format(
    audio_tensor: torch.Tensor,
    sample_rate: int,
    output_format: str
) -> bytes:
    """
    Convert audio tensor to specified format

    Args:
        audio_tensor: Audio as tensor (shape: [1, samples] or [samples])
        sample_rate: Sample rate of audio
        output_format: Target format (mp3, wav, opus, etc.)

    Returns:
        Audio data as bytes
    """
    # Ensure audio is 2D (channels, samples)
    if audio_tensor.dim() == 1:
        audio_tensor = audio_tensor.unsqueeze(0)

    # Move to CPU and convert to numpy
    audio_np = audio_tensor.cpu().numpy()

    # Convert to float32 if needed
    if audio_np.dtype != np.float32:
        audio_np = audio_np.astype(np.float32)

    # Create in-memory buffer
    buffer = io.BytesIO()

    if output_format == "pcm":
        # Raw PCM 16-bit
        audio_int16 = (audio_np * 32767).astype('int16')
        buffer.write(audio_int16.tobytes())

    elif output_format == "wav":
        # WAV format using soundfile
        sf.write(buffer, audio_np.T, sample_rate, format='WAV')

    elif output_format == "mp3":
        # MP3 format using ffmpeg subprocess
        try:
            # Write WAV to temp buffer first
            wav_buffer = io.BytesIO()
            sf.write(wav_buffer, audio_np.T, sample_rate, format='WAV')
            wav_buffer.seek(0)

            # Convert WAV to MP3 using ffmpeg
            process = subprocess.Popen(
                ['ffmpeg', '-i', 'pipe:0', '-f', 'mp3', '-q:a', '9', 'pipe:1'],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            mp3_data, err = process.communicate(input=wav_buffer.getvalue())

            if process.returncode != 0:
                logger.warning(f"FFmpeg MP3 encoding had issues, falling back to WAV")
                wav_buffer.seek(0)
                return wav_buffer.getvalue()

            return mp3_data
        except FileNotFoundError:
            logger.warning("FFmpeg not found, falling back to WAV format")
            wav_buffer = io.BytesIO()
            sf.write(wav_buffer, audio_np.T, sample_rate, format='WAV')
            return wav_buffer.getvalue()

    elif output_format == "flac":
        # FLAC format using soundfile
        sf.write(buffer, audio_np.T, sample_rate, format='FLAC')

    elif output_format in ["opus", "ogg"]:
        # Opus format - use ffmpeg since soundfile doesn't support it well
        try:
            wav_buffer = io.BytesIO()
            sf.write(wav_buffer, audio_np.T, sample_rate, format='WAV')
            wav_buffer.seek(0)

            process = subprocess.Popen(
                ['ffmpeg', '-i', 'pipe:0', '-f', 'ogg', '-c:a', 'libopus', 'pipe:1'],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            opus_data, err = process.communicate(input=wav_buffer.getvalue())

            if process.returncode != 0:
                logger.warning(f"FFmpeg Opus encoding failed, falling back to WAV")
                return wav_buffer.getvalue()

            return opus_data
        except FileNotFoundError:
            logger.warning("FFmpeg not found for Opus, falling back to WAV format")
            wav_buffer = io.BytesIO()
            sf.write(wav_buffer, audio_np.T, sample_rate, format='WAV')
            return wav_buffer.getvalue()

    elif output_format == "aac":
        # AAC format using ffmpeg
        try:
            wav_buffer = io.BytesIO()
            sf.write(wav_buffer, audio_np.T, sample_rate, format='WAV')
            wav_buffer.seek(0)

            process = subprocess.Popen(
                ['ffmpeg', '-i', 'pipe:0', '-f', 'adts', '-c:a', 'aac', 'pipe:1'],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            aac_data, err = process.communicate(input=wav_buffer.getvalue())

            if process.returncode != 0:
                logger.warning(f"FFmpeg AAC encoding failed, falling back to WAV")
                return wav_buffer.getvalue()

            return aac_data
        except FileNotFoundError:
            logger.warning("FFmpeg not found for AAC, falling back to WAV format")
            wav_buffer = io.BytesIO()
            sf.write(wav_buffer, audio_np.T, sample_rate, format='WAV')
            return wav_buffer.getvalue()
    else:
        raise ValueError(f"Unsupported audio format: {output_format}")

    return buffer.getvalue()


def get_content_type(format: str) -> str:
    """Get HTTP content type for audio format"""
    content_types = {
        "mp3": "audio/mpeg",
        "wav": "audio/wav",
        "opus": "audio/opus",
        "aac": "audio/aac",
        "flac": "audio/flac",
        "pcm": "application/octet-stream"
    }
    return content_types.get(format, "application/octet-stream")


# ============================================================================
# FastAPI Application
# ============================================================================

app = FastAPI(
    title="Chatterbox TTS - OpenAI Compatible API",
    description="OpenAI-compatible TTS API using Chatterbox",
    version="1.0.0"
)


@app.on_event("startup")
async def startup_event():
    """Load model on startup"""
    logger.info("Starting Chatterbox TTS API server...")
    try:
        model_manager.load_model()
        logger.info("Server ready to accept requests")
    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        raise


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Chatterbox TTS - OpenAI Compatible API",
        "endpoints": {
            "tts": "/v1/audio/speech",
            "voices": "/v1/audio/voices",
            "models": "/v1/models",
            "health": "/health"
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "model_loaded": model_manager.model is not None,
        "device": model_manager.device
    }


@app.get("/v1/models")
async def list_models():
    """
    List available TTS models (OpenAI-compatible)

    Returns list of available models in OpenAI format
    """
    return {
        "object": "list",
        "data": [
            {
                "id": "tts-1",
                "object": "model",
                "created": 1677610602,
                "owned_by": "chatterbox",
                "permission": [],
                "root": "tts-1",
                "parent": None
            },
            {
                "id": "tts-1-hd",
                "object": "model",
                "created": 1677610602,
                "owned_by": "chatterbox",
                "permission": [],
                "root": "tts-1-hd",
                "parent": None
            }
        ]
    }


@app.get("/v1/audio/voices")
async def list_voices():
    """
    List available voices (OpenAI-compatible)

    Returns list of available voice presets
    """
    voices = []
    for voice_id, voice_file in ServerConfig.VOICE_PRESETS.items():
        voice_path = ServerConfig.VOICE_SAMPLES_DIR / voice_file

        voices.append({
            "id": voice_id,
            "name": voice_id.capitalize(),
            "description": f"Voice clone based on {voice_file}",
            "preview_url": None,
            "available": voice_path.exists()
        })

    return {
        "object": "list",
        "data": voices
    }


@app.post("/v1/audio/speech")
async def create_speech(request: TTSRequest):
    """
    OpenAI-compatible TTS endpoint

    Generates audio from text using Chatterbox TTS with voice cloning
    """
    try:
        # Get model
        model = model_manager.model
        if model is None:
            raise HTTPException(status_code=503, detail="Model not loaded")

        # Get voice sample path
        try:
            voice_path = model_manager.get_voice_path(request.voice)
        except FileNotFoundError as e:
            raise HTTPException(status_code=400, detail=str(e))

        # Get generation parameters
        exaggeration = request.exaggeration or ServerConfig.DEFAULT_EXAGGERATION
        cfg_weight = request.cfg_weight or ServerConfig.DEFAULT_CFG_WEIGHT
        temperature = request.temperature or ServerConfig.DEFAULT_TEMPERATURE

        logger.info(f"Generating speech for voice='{request.voice}', "
                   f"format='{request.response_format}', stream={request.stream}, "
                   f"text_length={len(request.input)}")

        # Handle streaming vs non-streaming
        if request.stream:
            # Streaming response
            return StreamingResponse(
                stream_audio_generator(
                    model=model,
                    text=request.input,
                    voice_path=str(voice_path),
                    output_format=request.response_format,
                    exaggeration=exaggeration,
                    cfg_weight=cfg_weight,
                    temperature=temperature
                ),
                media_type=get_content_type(request.response_format),
                headers={
                    "Transfer-Encoding": "chunked",
                    "Cache-Control": "no-cache"
                }
            )
        else:
            # Non-streaming response
            audio_data = generate_complete_audio(
                model=model,
                text=request.input,
                voice_path=str(voice_path),
                output_format=request.response_format,
                exaggeration=exaggeration,
                cfg_weight=cfg_weight,
                temperature=temperature
            )

            return Response(
                content=audio_data,
                media_type=get_content_type(request.response_format)
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating speech: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


def generate_complete_audio(
    model: ChatterboxTTS,
    text: str,
    voice_path: str,
    output_format: str,
    exaggeration: float,
    cfg_weight: float,
    temperature: float
) -> bytes:
    """
    Generate complete audio (non-streaming)

    Returns complete audio file as bytes
    """
    start_time = time.time()

    # Generate audio
    audio_tensor = model.generate(
        text=text,
        audio_prompt_path=voice_path,
        exaggeration=exaggeration,
        cfg_weight=cfg_weight,
        temperature=temperature
    )

    generation_time = time.time() - start_time
    audio_duration = audio_tensor.shape[-1] / ServerConfig.SAMPLE_RATE
    rtf = generation_time / audio_duration if audio_duration > 0 else 0

    logger.info(f"Generated {audio_duration:.2f}s audio in {generation_time:.2f}s (RTF: {rtf:.3f})")

    # Convert to requested format
    audio_data = convert_audio_format(audio_tensor, ServerConfig.SAMPLE_RATE, output_format)

    return audio_data


def stream_audio_generator(
    model: ChatterboxTTS,
    text: str,
    voice_path: str,
    output_format: str,
    exaggeration: float,
    cfg_weight: float,
    temperature: float
) -> Generator[bytes, None, None]:
    """
    Generate streaming audio chunks

    Yields audio chunks as bytes in the requested format
    """
    logger.info("Starting streaming generation...")

    try:
        # Generate audio stream
        for audio_chunk, metrics in model.generate_stream(
            text=text,
            audio_prompt_path=voice_path,
            exaggeration=exaggeration,
            cfg_weight=cfg_weight,
            temperature=temperature,
            chunk_size=ServerConfig.DEFAULT_CHUNK_SIZE,
            context_window=ServerConfig.DEFAULT_CONTEXT_WINDOW,
            fade_duration=ServerConfig.DEFAULT_FADE_DURATION,
            print_metrics=False
        ):
            # Convert chunk to requested format
            chunk_data = convert_audio_format(
                audio_chunk,
                ServerConfig.SAMPLE_RATE,
                output_format
            )

            if metrics.chunk_count == 1:
                logger.info(f"First chunk latency: {metrics.latency_to_first_chunk:.3f}s")

            yield chunk_data

        logger.info(f"Streaming complete. Total chunks: {metrics.chunk_count}, "
                   f"RTF: {metrics.rtf:.3f}")

    except Exception as e:
        logger.error(f"Error in streaming generation: {e}", exc_info=True)
        raise


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """Run the server"""
    logger.info(f"Starting server on {ServerConfig.HOST}:{ServerConfig.PORT}")
    logger.info(f"Using device: {ServerConfig.MODEL_DEVICE}")
    logger.info(f"Voice samples directory: {ServerConfig.VOICE_SAMPLES_DIR}")

    uvicorn.run(
        app,
        host=ServerConfig.HOST,
        port=ServerConfig.PORT,
        log_level="info"
    )


if __name__ == "__main__":
    main()
