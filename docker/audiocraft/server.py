"""
Lightweight MusicGen API server.

Runs on CPU (no GPU required).  Loads the model lazily on first request.

Endpoints
---------
POST /generate         — generate music from a text prompt
GET  /health           — liveness check
GET  /status           — model loaded? + device info
"""

from __future__ import annotations

import io
import logging
import subprocess
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("audiocraft")

app = FastAPI(title="VidForge AudioCraft Server")

OUTPUT_DIR = Path("/app/output")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Lazy-loaded model ──────────────────────────────────────────────

_model = None


def _get_model():
    global _model
    if _model is None:
        from audiocraft.models import MusicGen

        logger.info("Loading musicgen-small on CPU (first request, may take a minute)…")
        _model = MusicGen.get_pretrained("facebook/musicgen-small", device="cpu")
        logger.info("Model loaded.")
    return _model


# ── Schemas ─────────────────────────────────────────────────────────


class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=500)
    duration: float = Field(10.0, ge=1.0, le=120.0)
    output_format: str = Field("wav", pattern="^(wav|mp3)$")


class GenerateResponse(BaseModel):
    filename: str
    path: str
    duration: float
    sample_rate: int


# ── Endpoints ───────────────────────────────────────────────────────


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/status")
async def status():
    return {
        "model_loaded": _model is not None,
        "model": "facebook/musicgen-small",
        "device": "cpu",
    }


@app.post("/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest):
    model = _get_model()
    model.set_generation_params(duration=req.duration)

    logger.info(f"Generating {req.duration}s of music: {req.prompt[:80]}…")
    wav = model.generate([req.prompt])
    wav = wav.cpu()

    base_name = f"musicgen_{uuid.uuid4().hex[:8]}"
    wav_path = OUTPUT_DIR / f"{base_name}.wav"

    # Save WAV via soundfile
    import soundfile as sf
    import numpy as np

    sample_rate = model.sample_rate
    audio_np = wav[0].numpy()  # shape: (channels, samples) or (samples,)
    # soundfile expects (samples, channels)
    if audio_np.ndim == 2:
        audio_np = audio_np.T
    sf.write(str(wav_path), audio_np, sample_rate)
    logger.info(f"Saved WAV: {wav_path} shape={audio_np.shape}")

    # Optionally convert to mp3 (smaller file)
    final_path = wav_path
    if req.output_format == "mp3":
        mp3_path = OUTPUT_DIR / f"{base_name}.mp3"
        proc = subprocess.run(
            ["ffmpeg", "-y", "-i", str(wav_path), "-b:a", "192k", str(mp3_path)],
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0:
            wav_path.unlink(missing_ok=True)
            final_path = mp3_path

    actual_duration = wav.shape[-1] / sample_rate

    logger.info(f"Generated {final_path.name} ({actual_duration:.1f}s)")

    return GenerateResponse(
        filename=final_path.name,
        path=str(final_path),
        duration=actual_duration,
        sample_rate=sample_rate,
    )


@app.get("/files/{filename}")
async def get_file(filename: str):
    path = OUTPUT_DIR / filename
    if not path.exists():
        raise HTTPException(404, "File not found")
    return FileResponse(path, media_type="audio/wav", filename=filename)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=5000)
