"""
OpenAI-compatible TTS API server for Chatterbox
Implements /v1/audio/speech endpoint compatible with OpenAI's TTS API
"""

import io
import logging
import os
import re
import sys
import subprocess
import threading
from pathlib import Path
from typing import Literal, Optional, Generator
import time

import torch
import torchaudio
import soundfile as sf
import numpy as np
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, validator
import uvicorn

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from chatterbox.tts_turbo import ChatterboxTurboTTS, Conditionals

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
    # Use cuda:0 directly (shared with main LLM)
    MODEL_DEVICE = "cuda:0"

    # Voice samples directory
    VOICE_SAMPLES_DIR = Path(__file__).parent

    # Voice presets mapping
    # Note: Chatterbox Turbo has ONE default voice in conds.pt
    # All other voices require audio sample files for voice cloning
    VOICE_PRESETS = {
        # Default voice (uses built-in conds.pt when no sample file specified).
        # This is the ONLY hardcoded entry — it has no sample file so it can't
        # be auto-discovered. Every other voice is registered from its audio
        # file at boot by discover_voices(), so custom presets aren't listed
        # here: renaming a file just changes its id on the next restart, with
        # no dead entries left behind.
        "her": None,  # Default voice (built-in)
    }

    # Audio extensions treated as voice samples during auto-detection
    VOICE_FILE_EXTENSIONS = (".mp3", ".wav", ".flac")

    # Filename stems to skip when auto-detecting (test/output artifacts)
    VOICE_IGNORE_PREFIXES = ("test_", "test-", "test_output", "output")

    @staticmethod
    def _slugify_voice_id(stem: str) -> str:
        """Turn a filename stem into a clean voice id (lowercase, hyphenated)."""
        slug = stem.strip().lower()
        slug = re.sub(r"[\s_]+", "-", slug)
        slug = re.sub(r"[^a-z0-9-]", "", slug)
        slug = re.sub(r"-+", "-", slug).strip("-")
        return slug

    @classmethod
    def discover_voices(cls):
        """
        Scan VOICE_SAMPLES_DIR for audio files and register any that aren't
        already mapped by an explicit preset above. Curated presets take
        priority (their IDs and filenames are preserved); this only adds
        newly-dropped sample files so they appear without a code change.
        """
        known_files = {f for f in cls.VOICE_PRESETS.values() if f}
        added = 0
        for path in sorted(cls.VOICE_SAMPLES_DIR.iterdir()):
            if not path.is_file() or path.suffix.lower() not in cls.VOICE_FILE_EXTENSIONS:
                continue
            if path.name in known_files:
                continue  # already registered under a curated id
            if path.stem.lower().startswith(cls.VOICE_IGNORE_PREFIXES):
                logger.debug(f"Skipping non-voice audio file: {path.name}")
                continue
            voice_id = cls._slugify_voice_id(path.stem)
            if not voice_id or voice_id in cls.VOICE_PRESETS:
                continue
            cls.VOICE_PRESETS[voice_id] = path.name
            added += 1
            logger.info(f"Auto-detected voice '{voice_id}' -> {path.name}")
        logger.info(
            f"Voice presets ready: {len(cls.VOICE_PRESETS)} total "
            f"({added} auto-detected)"
        )

    # TTS generation defaults (Chatterbox Turbo)
    # Note: Turbo does not support exaggeration or cfg_weight
    # These parameters are ignored by the Turbo model
    DEFAULT_TEMPERATURE = 0.8
    DEFAULT_TOP_P = 0.95
    DEFAULT_TOP_K = 1000
    DEFAULT_REPETITION_PENALTY = 1.2
    DEFAULT_NORM_LOUDNESS = True
    
    # Streaming settings
    DEFAULT_CHUNK_SIZE = 25
    DEFAULT_CONTEXT_WINDOW = 50
    DEFAULT_FADE_DURATION = 0.02

    # Text chunking settings
    MAX_CHUNK_CHARS = 250  # Max characters per chunk sent to the model
    CROSSFADE_SAMPLES = 2400  # 100ms crossfade at 24kHz between chunks

    # Audio output settings
    SAMPLE_RATE = 24000  # S3GEN_SR from Chatterbox

    # Concurrency: max simultaneous GPU generations. Extra requests queue (FIFO)
    # rather than all contending for the same GPU at once.
    #
    # Set to 1 based on benchmarking (see performance-test-results.md): on a
    # single (and here, contended) GPU, concurrency does not add throughput —
    # 3-way parallel is ~2x SLOWER in total than sequential and delays the first
    # response. Serializing GPU work is optimal, and mp3 encoding runs outside
    # this lock so CPU encode still overlaps the next request's GPU work.
    # Raise this only if TTS moves to a dedicated GPU with real headroom.
    MAX_IN_FLIGHT = 1


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

    # Extended parameters for Chatterbox Turbo
    # Note: exaggeration and cfg_weight are not supported by Turbo
    exaggeration: Optional[float] = Field(
        default=None,
        description="Emotion exaggeration (not supported by Turbo model)",
        ge=0.0,
        le=1.0
    )
    cfg_weight: Optional[float] = Field(
        default=None,
        description="Classifier-free guidance weight (not supported by Turbo)",
        ge=0.0,
        le=5.0
    )
    temperature: Optional[float] = Field(
        default=None,
        description="Sampling temperature",
        ge=0.1,
        le=2.0
    )
    top_k: Optional[int] = Field(
        default=None,
        description="Top-k sampling (Turbo only)",
        ge=1,
        le=1000
    )
    top_p: Optional[float] = Field(
        default=None,
        description="Top-p (nucleus) sampling",
        ge=0.0,
        le=1.0
    )
    repetition_penalty: Optional[float] = Field(
        default=None,
        description="Repetition penalty",
        ge=1.0,
        le=2.0
    )
    norm_loudness: Optional[bool] = Field(
        default=None,
        description="Normalize loudness to -27 LUFS"
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
        self.model: Optional[ChatterboxTurboTTS] = None
        self.device = ServerConfig.MODEL_DEVICE
        # Per-voice conditionals, encoded once and kept resident in VRAM.
        # Memory-only by design: the audio files are the single source of truth,
        # so swapping a voice is just "replace the file + restart" — there is no
        # stale on-disk cache to invalidate.
        self.voice_conds: dict[str, Conditionals] = {}

    def load_model(self):
        """Load the Chatterbox Turbo TTS model"""
        if self.model is None:
            logger.info(f"Loading Chatterbox Turbo TTS model on device: {self.device}")
            try:
                self.model = ChatterboxTurboTTS.from_pretrained(device=self.device)
                logger.info("Turbo model loaded successfully")
            except Exception as e:
                logger.error(f"Failed to load model: {e}")
                raise
        return self.model

    def build_voice_cache(self):
        """
        Encode every discovered voice into a Conditionals object once and hold
        them all in VRAM. Runs at startup, after discover_voices() and the model
        load. The built-in 'her' voice already carries its conditionals on the
        model, so we reuse those directly.
        """
        built = 0
        t_start = time.time()
        for voice_id, voice_file in ServerConfig.VOICE_PRESETS.items():
            try:
                if voice_file is None:
                    # Built-in default voice: model.conds is already populated.
                    if self.model.conds is not None:
                        self.voice_conds[voice_id] = self.model.conds
                    continue
                path = ServerConfig.VOICE_SAMPLES_DIR / voice_file
                if not path.exists():
                    logger.warning(f"Skipping voice '{voice_id}': file not found ({path})")
                    continue
                t0 = time.time()
                self.voice_conds[voice_id] = self.model.build_conditionals(str(path))
                built += 1
                logger.info(f"Cached voice conds '{voice_id}' in {time.time() - t0:.2f}s")
            except Exception as e:
                logger.warning(f"Failed to cache conds for '{voice_id}': {e}")
        logger.info(
            f"Voice conds cache ready: {len(self.voice_conds)} voices resident in VRAM "
            f"({built} encoded) in {time.time() - t_start:.1f}s"
        )

    def get_conds(self, voice_name: str) -> Conditionals:
        """
        Return the cached Conditionals for a voice. Falls back to encoding on
        first use if a voice somehow isn't in the boot-time cache (e.g. a file
        dropped in after startup), then caches it.
        """
        conds = self.voice_conds.get(voice_name)
        if conds is not None:
            return conds

        # Lazy fallback — should be rare once build_voice_cache() has run.
        voice_path = self.get_voice_path(voice_name)  # may raise FileNotFoundError
        if voice_path is None:
            conds = self.model.conds  # built-in voice
        else:
            logger.info(f"Voice '{voice_name}' not pre-cached; encoding on first use")
            conds = self.model.build_conditionals(voice_path)
        self.voice_conds[voice_name] = conds
        return conds

    def get_voice_path(self, voice_name: str) -> Optional[str]:
        """
        Get the path to voice sample file or None for default built-in voice.
        
        Returns:
            - Path to voice sample file for custom voices
            - None for default built-in voice (uses model's conds.pt)
            - Raises FileNotFoundError if voice sample file not found
        """
        voice_file = ServerConfig.VOICE_PRESETS.get(voice_name)
        
        # Voice not in presets
        if voice_file is None and voice_name not in ServerConfig.VOICE_PRESETS:
            logger.warning(f"Unknown voice '{voice_name}', using default voice")
            return None
        
        # Default voice (None value means use built-in conds.pt)
        if voice_file is None:
            logger.debug(f"Using default built-in voice: {voice_name}")
            return None
        
        # Custom voice with sample file
        voice_path = ServerConfig.VOICE_SAMPLES_DIR / voice_file

        if not voice_path.exists():
            logger.warning(f"Voice file not found: {voice_path}")
            # Try alternative extensions
            for ext in [".mp3", ".wav", ".flac"]:
                alt_path = voice_path.with_suffix(ext)
                if alt_path.exists():
                    logger.info(f"Using alternative voice file: {alt_path}")
                    return str(alt_path)
            raise FileNotFoundError(f"Voice sample not found: {voice_path}")

        return str(voice_path)


model_manager = ModelManager()

# Bounds how many requests run GPU generation at once. Acquired inside the
# threadpool worker that runs model.generate(), so it applies to both the
# streaming and non-streaming paths.
_gpu_slots = threading.Semaphore(ServerConfig.MAX_IN_FLIGHT)


# ============================================================================
# Text Chunking
# ============================================================================

def split_text_into_chunks(text: str, max_chars: int = ServerConfig.MAX_CHUNK_CHARS) -> list[str]:
    """
    Split long text into chunks suitable for TTS generation.

    Splits on sentence boundaries first, then falls back to clause boundaries
    (commas, semicolons, dashes) if a sentence is still too long.
    Preserves punctuation so the model gets proper intonation cues.
    """
    if len(text) <= max_chars:
        return [text]

    # Split into sentences (keep the delimiter attached)
    sentence_pattern = re.compile(r'(?<=[.!?])\s+')
    sentences = sentence_pattern.split(text.strip())

    chunks = []
    current_chunk = ""

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        # If adding this sentence keeps us under the limit, accumulate
        if current_chunk and len(current_chunk) + len(sentence) + 1 <= max_chars:
            current_chunk += " " + sentence
        elif not current_chunk and len(sentence) <= max_chars:
            current_chunk = sentence
        else:
            # Flush the current chunk if we have one
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = ""

            # If the sentence itself is too long, split on clause boundaries
            if len(sentence) > max_chars:
                clause_parts = re.split(r'(?<=[,;\-])\s+', sentence)
                for part in clause_parts:
                    part = part.strip()
                    if not part:
                        continue
                    if current_chunk and len(current_chunk) + len(part) + 1 <= max_chars:
                        current_chunk += " " + part
                    else:
                        if current_chunk:
                            chunks.append(current_chunk)
                        current_chunk = part
            else:
                current_chunk = sentence

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def crossfade_audio(chunks: list[torch.Tensor], fade_samples: int = ServerConfig.CROSSFADE_SAMPLES) -> torch.Tensor:
    """
    Concatenate audio chunks with a short crossfade to avoid clicks/pops.
    """
    if len(chunks) == 1:
        return chunks[0]

    # Ensure all chunks are 1D
    processed = []
    for c in chunks:
        if c.dim() > 1:
            c = c.squeeze(0)
        processed.append(c)

    result = processed[0]
    for next_chunk in processed[1:]:
        overlap = min(fade_samples, result.shape[0], next_chunk.shape[0])
        if overlap > 0:
            fade_out = torch.linspace(1.0, 0.0, overlap, device=result.device)
            fade_in = torch.linspace(0.0, 1.0, overlap, device=next_chunk.device)
            # Blend the overlap region
            result_tail = result[-overlap:] * fade_out
            next_head = next_chunk[:overlap] * fade_in
            blended = result_tail + next_head
            result = torch.cat([result[:-overlap], blended, next_chunk[overlap:]])
        else:
            result = torch.cat([result, next_chunk])

    return result.unsqueeze(0)  # Back to [1, samples]


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
                ['ffmpeg', '-i', 'pipe:0', '-f', 'mp3', '-q:a', '2', 'pipe:1'],
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
        ServerConfig.discover_voices()
        model_manager.load_model()
        model_manager.build_voice_cache()
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
            "voices_voxta": "/v1/audio/voices/voxta",
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
        # Default voice (uses model's built-in conds.pt)
        if voice_file is None:
            description = "Default Chatterbox Turbo voice"
            available = True
        else:
            # Custom voice with sample file
            voice_path = ServerConfig.VOICE_SAMPLES_DIR / voice_file
            description = f"Voice clone based on {voice_file}"
            available = voice_path.exists()

        voices.append({
            "id": voice_id,
            "name": voice_id.capitalize(),
            "description": description,
            "preview_url": None,
            "available": available
        })

    return {
        "object": "list",
        "data": voices
    }


@app.get("/v1/audio/voices/voxta")
async def list_voices_voxta():
    """
    List available voices in Voxta-compatible format

    Returns list of available voice presets as a direct array
    for compatibility with Voxta's dynamic voice discovery.
    """
    voices = []
    for voice_id, voice_file in ServerConfig.VOICE_PRESETS.items():
        # Default voice (uses model's built-in conds.pt)
        if voice_file is None:
            description = "Default Chatterbox Turbo voice"
            available = True
        else:
            # Custom voice with sample file
            voice_path = ServerConfig.VOICE_SAMPLES_DIR / voice_file
            description = f"Voice clone based on {voice_file}"
            available = voice_path.exists()

        voices.append({
            "id": voice_id,
            "name": voice_id.capitalize(),
            "description": description,
            "preview_url": None,
            "available": available
        })

    return voices


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

        # Resolve the voice to its cached (VRAM-resident) conditionals.
        try:
            conds = model_manager.get_conds(request.voice)
        except FileNotFoundError as e:
            raise HTTPException(status_code=400, detail=str(e))

        # Get generation parameters (Turbo-specific)
        # Note: exaggeration and cfg_weight are not supported by Turbo
        temperature = request.temperature or ServerConfig.DEFAULT_TEMPERATURE
        top_k = request.top_k or ServerConfig.DEFAULT_TOP_K
        top_p = request.top_p or ServerConfig.DEFAULT_TOP_P
        repetition_penalty = request.repetition_penalty or ServerConfig.DEFAULT_REPETITION_PENALTY
        norm_loudness = request.norm_loudness if request.norm_loudness is not None else ServerConfig.DEFAULT_NORM_LOUDNESS

        # Warn if user tried to use unsupported parameters
        if request.exaggeration is not None or request.cfg_weight is not None:
            logger.warning("exaggeration and cfg_weight are not supported by Chatterbox Turbo and will be ignored")

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
                    conds=conds,  # cached, VRAM-resident per-voice conditionals
                    output_format=request.response_format,
                    temperature=temperature,
                    top_k=top_k,
                    top_p=top_p,
                    repetition_penalty=repetition_penalty,
                    norm_loudness=norm_loudness
                ),
                media_type=get_content_type(request.response_format),
                headers={
                    "Transfer-Encoding": "chunked",
                    "Cache-Control": "no-cache"
                }
            )
        else:
            # Non-streaming response.
            # generate_complete_audio() does blocking GPU work; run it in a
            # threadpool so it doesn't stall uvicorn's event loop and serialise
            # concurrent requests (e.g. simultaneous agents in a group turn).
            audio_data = await run_in_threadpool(
                generate_complete_audio,
                model=model,
                text=request.input,
                conds=conds,  # cached, VRAM-resident per-voice conditionals
                output_format=request.response_format,
                temperature=temperature,
                top_k=top_k,
                top_p=top_p,
                repetition_penalty=repetition_penalty,
                norm_loudness=norm_loudness
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
    model: ChatterboxTurboTTS,
    text: str,
    conds: Conditionals,
    output_format: str,
    temperature: float,
    top_k: int,
    top_p: float,
    repetition_penalty: float,
    norm_loudness: bool
) -> bytes:
    """
    Generate complete audio (non-streaming)

    Returns complete audio file as bytes

    Args:
        conds: Cached per-voice conditionals (built once at startup)
    """
    start_time = time.time()

    # Split long text into chunks to prevent model degradation
    text_chunks = split_text_into_chunks(text)

    if len(text_chunks) > 1:
        logger.info(f"Split text into {len(text_chunks)} chunks for generation")

    # Hold one GPU slot for the whole generation (all chunks); format conversion
    # below runs outside the slot so it doesn't hog the GPU cap.
    audio_chunks = []
    with _gpu_slots:
        for i, chunk_text in enumerate(text_chunks):
            logger.debug(f"Generating chunk {i+1}/{len(text_chunks)}: {chunk_text[:60]}...")
            chunk_audio = model.generate(
                text=chunk_text,
                conds=conds,
                temperature=temperature,
                top_k=top_k,
                top_p=top_p,
                repetition_penalty=repetition_penalty,
                norm_loudness=norm_loudness,
            )
            audio_chunks.append(chunk_audio)

    # Concatenate chunks with crossfade
    if len(audio_chunks) == 1:
        audio_tensor = audio_chunks[0]
    else:
        audio_tensor = crossfade_audio(audio_chunks)

    generation_time = time.time() - start_time
    audio_duration = audio_tensor.shape[-1] / ServerConfig.SAMPLE_RATE
    rtf = generation_time / audio_duration if audio_duration > 0 else 0

    logger.info(f"Turbo generated {audio_duration:.2f}s audio in {generation_time:.2f}s (RTF: {rtf:.3f})")

    # Convert to requested format
    audio_data = convert_audio_format(audio_tensor, ServerConfig.SAMPLE_RATE, output_format)

    return audio_data


def stream_audio_generator(
    model: ChatterboxTurboTTS,
    text: str,
    conds: Conditionals,
    output_format: str,
    temperature: float,
    top_k: int,
    top_p: float,
    repetition_penalty: float,
    norm_loudness: bool
) -> Generator[bytes, None, None]:
    """
    Generate streaming audio chunks compatible with OpenAI TTS streaming format

    For proper streaming, sends WAV header once then raw PCM chunks.
    This allows clients to receive and play audio progressively.

    Note: Turbo model does not support exaggeration or cfg_weight.

    Args:
        conds: Cached per-voice conditionals (built once at startup)
    """
    logger.info(f"Starting streaming generation (format: {output_format})...")

    try:
        # Generate full audio with text chunking (shared by both paths)
        text_chunks = split_text_into_chunks(text)
        if len(text_chunks) > 1:
            logger.info(f"Streaming: split text into {len(text_chunks)} chunks")

        # Hold one GPU slot for the whole generation; byte streaming below runs
        # outside the slot.
        audio_parts = []
        with _gpu_slots:
            for i, chunk_text in enumerate(text_chunks):
                logger.debug(f"Streaming chunk {i+1}/{len(text_chunks)}: {chunk_text[:60]}...")
                part = model.generate(
                    text=chunk_text,
                    conds=conds,
                    temperature=temperature,
                    top_k=top_k,
                    top_p=top_p,
                    repetition_penalty=repetition_penalty,
                    norm_loudness=norm_loudness,
                )
                audio_parts.append(part)

        if len(audio_parts) == 1:
            audio_tensor = audio_parts[0]
        else:
            audio_tensor = crossfade_audio(audio_parts)

        # For WAV streaming: Send header once, then raw PCM chunks
        if output_format == "wav":
            # Convert to numpy for processing
            audio_np = audio_tensor.cpu().numpy()
            if audio_np.ndim > 1:
                audio_np = audio_np.squeeze(0)

            # Ensure float32
            if audio_np.dtype != np.float32:
                audio_np = audio_np.astype(np.float32)

            # Generate WAV header
            wav_buffer = io.BytesIO()
            sf.write(wav_buffer, audio_np, ServerConfig.SAMPLE_RATE, format='WAV')
            wav_buffer.seek(0)
            wav_data = wav_buffer.getvalue()

            # Extract header (first 44 bytes for standard WAV, or find data chunk)
            # Standard WAV header is 44 bytes, but we'll find the "data" chunk marker
            header_end = wav_data.find(b'data') + 8  # "data" + 4 bytes size
            wav_header = wav_data[:header_end]

            # Yield header first
            logger.info("Sending WAV header")
            yield wav_header

            # Yield audio in chunks
            chunk_size = ServerConfig.DEFAULT_CHUNK_SIZE * ServerConfig.SAMPLE_RATE // 1000  # Convert ms to samples
            chunk_size = max(chunk_size, 4096)  # At least 4KB chunks

            for i in range(0, len(audio_np), chunk_size):
                chunk = audio_np[i:i + chunk_size]
                # Convert to raw PCM bytes (int16)
                chunk_int16 = (chunk * 32767).astype('int16')
                chunk_bytes = chunk_int16.tobytes()
                yield chunk_bytes

                if i == 0:
                    logger.info(f"First audio chunk sent (chunk size: {len(chunk_bytes)} bytes)")

            logger.info(f"Streaming complete. Total audio: {len(audio_np)/ServerConfig.SAMPLE_RATE:.2f}s")

        else:
            # For non-WAV formats, convert full audio then stream in byte chunks
            audio_data = convert_audio_format(
                audio_tensor,
                ServerConfig.SAMPLE_RATE,
                output_format
            )

            # Stream in chunks
            chunk_size = 8192  # 8KB chunks for encoded formats
            for i in range(0, len(audio_data), chunk_size):
                chunk = audio_data[i:i + chunk_size]
                yield chunk

                if i == 0:
                    logger.info(f"First chunk sent ({output_format}, size: {len(chunk)} bytes)")

            logger.info(f"Streaming complete. Total size: {len(audio_data)} bytes ({output_format})")

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
