"""NOVA's speech server: Sara's Saudi voice behind an OpenAI-style `/audio/speech`.

The backend's `OpenAISpeechSynthesizer` (nova_backend/app/integrations/voice/
speech.py) posts here. llama.cpp, which served the text model until vLLM
replaced it (ADR-0019), cannot serve Qwen3-TTS (ADR-0018), so this is the
smallest server that can: the `qwen-tts`
package running the community Saudi fine-tune `vadimbelsky/qwen3-TTS-KSA`
(Apache-2.0, one speaker, `ksa_speaker`, Arabic only).

The model speaks at 24 kHz and a phone line carries 8 kHz, and the backend
refuses any clip that is not mono PCM WAV at the rate it asked for. So every
clip is resampled here to the request's `sample_rate` and written as 16-bit PCM.

One clip is generated at a time (`_generate_lock`): a GPU shared between calls
only makes each caller wait longer, and the backend's own timeout already sends
a slow reply to Unifonic's voice instead.

Configuration, all optional:
    TTS_MODEL        Hugging Face id or local path (vadimbelsky/qwen3-TTS-KSA)
    TTS_DEVICE       cuda:0 when a GPU is visible, else cpu
    TTS_DTYPE        bfloat16 (float32 doubles the memory for no audible gain)
    TTS_API_KEY      when set, requests must send `Authorization: Bearer <key>`
    TTS_MAX_CHARS    longest text accepted (600)
"""

import asyncio
import hmac
import io
import logging
import os
import time
from contextlib import asynccontextmanager
from math import gcd
from typing import Any

import numpy as np
import soundfile as sf
import torch
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from qwen_tts import Qwen3TTSModel
from scipy.signal import resample_poly

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("nova.tts")

MODEL_ID = os.environ.get("TTS_MODEL", "vadimbelsky/qwen3-TTS-KSA")
DEVICE = os.environ.get("TTS_DEVICE") or ("cuda:0" if torch.cuda.is_available() else "cpu")
DTYPE = getattr(torch, os.environ.get("TTS_DTYPE", "bfloat16"))
API_KEY = os.environ.get("TTS_API_KEY") or None
MAX_CHARS = int(os.environ.get("TTS_MAX_CHARS", "600"))
#: Phone audio is 8 kHz; 16 and 24 kHz are allowed for anything else.
SAMPLE_RATES = frozenset({8000, 16000, 24000})

_model: Qwen3TTSModel | None = None
_generate_lock = asyncio.Lock()


@asynccontextmanager
async def lifespan(_: FastAPI):
    global _model
    started = time.perf_counter()
    _model = Qwen3TTSModel.from_pretrained(
        MODEL_ID, device_map=DEVICE, dtype=DTYPE, attn_implementation="sdpa"
    )
    logger.info(
        "tts_model_loaded model=%s device=%s dtype=%s seconds=%.1f speakers=%s languages=%s",
        MODEL_ID,
        DEVICE,
        DTYPE,
        time.perf_counter() - started,
        _model.get_supported_speakers(),
        _model.get_supported_languages(),
    )
    yield


app = FastAPI(title="NOVA TTS", lifespan=lifespan, docs_url=None, redoc_url=None)


class SpeechRequest(BaseModel):
    """OpenAI's `/audio/speech` body, with the fields the backend adds."""

    model: str | None = None
    input: str = Field(min_length=1)
    voice: str = "ksa_speaker"
    response_format: str = "wav"
    language: str = "Arabic"
    sample_rate: int = 8000
    instructions: str = ""


def _authorize(authorization: str | None) -> None:
    if API_KEY is None:
        return
    supplied = (authorization or "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(supplied.encode(), API_KEY.encode()):
        raise HTTPException(status_code=401, detail="invalid API key")


def _phone_wav(audio: np.ndarray, source_rate: int, target_rate: int) -> bytes:
    """Mono 16-bit PCM WAV at `target_rate`."""
    samples = np.asarray(audio, dtype=np.float32).reshape(-1)
    if source_rate != target_rate:
        common = gcd(source_rate, target_rate)
        samples = resample_poly(samples, target_rate // common, source_rate // common)
    samples = np.clip(samples, -1.0, 1.0)
    out = io.BytesIO()
    sf.write(out, samples, target_rate, format="WAV", subtype="PCM_16")
    return out.getvalue()


def _synthesize(body: SpeechRequest) -> bytes:
    assert _model is not None
    wavs, rate = _model.generate_custom_voice(
        text=body.input,
        speaker=body.voice,
        language=body.language,
        instruct=body.instructions or None,
    )
    return _phone_wav(wavs[0], rate, body.sample_rate)


@app.post("/v1/audio/speech")
async def speech(body: SpeechRequest, authorization: str | None = Header(default=None)):
    """The clip, as `audio/wav`. A refusal is a 4xx with the reason, which the
    backend logs before Unifonic's own voice reads the text instead."""
    _authorize(authorization)
    if body.response_format != "wav":
        raise HTTPException(status_code=400, detail="only response_format=wav is served")
    if body.sample_rate not in SAMPLE_RATES:
        raise HTTPException(status_code=400, detail=f"sample_rate must be one of {sorted(SAMPLE_RATES)}")
    if len(body.input) > MAX_CHARS:
        raise HTTPException(status_code=400, detail=f"input longer than {MAX_CHARS} characters")
    started = time.perf_counter()
    async with _generate_lock:
        try:
            audio = await asyncio.to_thread(_synthesize, body)
        except ValueError as exc:
            # An unknown speaker or language: the library names the ones it has.
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info(
        "tts_generated chars=%d seconds=%.2f", len(body.input), time.perf_counter() - started
    )
    return Response(content=audio, media_type="audio/wav")


@app.get("/v1/models")
async def models(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _authorize(authorization)
    return {"object": "list", "data": [{"id": MODEL_ID, "object": "model", "owned_by": "nova"}]}


@app.get("/health")
async def health() -> dict[str, str]:
    # Lifespan finishes loading before the server accepts a request, so an
    # answer here means the model is in memory.
    return {"status": "ok"}
