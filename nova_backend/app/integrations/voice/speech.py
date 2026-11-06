"""Sara's voice: text-to-speech over an OpenAI-compatible `/audio/speech` server.

Infrastructure only. The server is NOVA's own `tts` compose service
(`infra/tts`, ADR-0018), running Qwen3-TTS through its `qwen-tts` package:
Qwen3-TTS does not ship Arabic, so the model is the community Saudi fine-tune
`vadimbelsky/qwen3-TTS-KSA` (Apache-2.0; one baked-in voice, `ksa_speaker`;
its authors call it not production-ready). Any server answering the same
request works, so changing the voice is configuration (`VOICE_TTS_*`).

The request is OpenAI's `POST /audio/speech`: `model`, `input`, `voice` and
`response_format`, plus `language`, `sample_rate` (8000: a phone line's rate)
and `instructions`, as vLLM-Omni also takes them. The answer is the whole clip
as WAV.

Speech is never required. Unset, slow, failing, or asked for a language it
does not speak, the synthesiser answers None and Unifonic's own voice reads the
text. A caller hears Sara either way.

What comes back is checked before it is kept: a WAV, mono, PCM, at the rate
asked for. Anything else (an error page answered with 200, MP3, 24 kHz because
the server ignored `sample_rate`) would be cached for an hour and played as
noise, so it is refused and Unifonic reads the text.

Generated audio is kept in Redis (`AudioStore`) for Unifonic to fetch, keyed
by an HMAC of voice and words. The key is the audio's URL: unguessable without
the secret, and the same words said again (a greeting, "press 1") are served
without generating them twice.
"""

import hashlib
import hmac
import io
import logging
import time
import wave
from typing import Any, Protocol

import httpx

logger = logging.getLogger(__name__)


class SpeechSynthesizer(Protocol):
    @property
    def identity(self) -> str:
        """The voice: model, speaker and settings. Clips are cached per voice."""
        ...

    async def synthesize(
        self, text: str, *, locale: str, timeout_seconds: float | None = None
    ) -> bytes | None:
        """WAV audio of `text`, or None when this voice should not say it.

        `timeout_seconds`, when given, shortens the voice's own timeout: what is
        left of the caller's turn.
        """
        ...


class OpenAISpeechSynthesizer:
    """`POST {base_url}/audio/speech` on an OpenAI-compatible speech server."""

    def __init__(
        self,
        base_url: str,
        model: str,
        voice: str,
        api_key: str | None = None,
        language: str = "Arabic",
        locales: frozenset[str] = frozenset({"ar"}),
        instructions: str = "",
        sample_rate: int = 8000,
        timeout_seconds: float = 4.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.voice = voice
        self.api_key = api_key
        self.language = language
        #: The locales this voice speaks. The KSA fine-tune speaks Arabic only.
        self.locales = locales
        self.instructions = instructions
        self.sample_rate = sample_rate
        self.timeout_seconds = timeout_seconds
        #: For tests: an `httpx.MockTransport` in place of the network.
        self.transport = transport

    @property
    def identity(self) -> str:
        """What makes two clips of the same words differ: part of the cache key."""
        return f"{self.model}|{self.voice}|{self.language}|{self.sample_rate}|{self.instructions}"

    async def synthesize(
        self, text: str, *, locale: str, timeout_seconds: float | None = None
    ) -> bytes | None:
        if locale[:2] not in self.locales or not text.strip():
            return None
        timeout = self.timeout_seconds
        if timeout_seconds is not None:
            timeout = min(timeout, timeout_seconds)
        body: dict[str, Any] = {
            "model": self.model,
            "input": text,
            "voice": self.voice,
            "response_format": "wav",
            "language": self.language,
            "sample_rate": self.sample_rate,
        }
        if self.instructions:
            body["instructions"] = self.instructions
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=timeout, transport=self.transport) as client:
                response = await client.post(
                    f"{self.base_url}/audio/speech", json=body, headers=headers
                )
        except httpx.HTTPError as exc:
            # A timeout lands here too: Unifonic's voice reads it instead.
            logger.warning("voice_tts_unavailable", extra={"error": repr(exc)})
            return None
        if not response.is_success or not response.content:
            logger.warning(
                "voice_tts_refused",
                extra={"status": response.status_code, "body": response.text[:300]},
            )
            return None
        problem = wav_problem(response.content, sample_rate=self.sample_rate)
        if problem is not None:
            logger.warning("voice_tts_not_phone_audio", extra={"problem": problem})
            return None
        logger.info(
            "voice_tts_generated",
            extra={"seconds": round(time.perf_counter() - started, 2), "chars": len(text)},
        )
        return response.content


def wav_problem(audio: bytes, *, sample_rate: int) -> str | None:
    """Why `audio` is not a clip a phone line can play, or None when it is:
    a PCM WAV, one channel, at `sample_rate`, with sound in it."""
    try:
        with wave.open(io.BytesIO(audio)) as clip:
            channels, rate, frames = clip.getnchannels(), clip.getframerate(), clip.getnframes()
    except (wave.Error, EOFError) as exc:
        # Not RIFF/WAVE, truncated, or not PCM: `wave` reads PCM only.
        return f"not a PCM WAV: {exc}"
    if channels != 1:
        return f"{channels} channels, not mono"
    if rate != sample_rate:
        return f"{rate} Hz, not {sample_rate}"
    if frames == 0:
        return "no audio"
    return None


class AudioStore(Protocol):
    async def get(self, key: str) -> bytes | None: ...

    async def put(self, key: str, audio: bytes, ttl_seconds: int) -> bool:
        """Keeps the clip. False when it was not kept: then no link may name it."""
        ...


class RedisAudioStore:
    """Clips in Redis with a TTL. Unreachable Redis: nothing kept, nothing served,
    and `put` says so, so Unifonic reads the text rather than fetch a 404."""

    def __init__(self, redis: Any) -> None:
        self._redis = redis

    @classmethod
    def from_url(cls, url: str) -> "RedisAudioStore":
        try:
            from redis.asyncio import Redis

            client: Any = Redis.from_url(url)
        except Exception:
            logger.warning("voice_audio_store_unavailable", exc_info=True)
            client = None
        return cls(client)

    @staticmethod
    def _name(key: str) -> str:
        return f"voice:audio:{key}"

    async def get(self, key: str) -> bytes | None:
        if self._redis is None:
            return None
        try:
            return await self._redis.get(self._name(key))
        except Exception:
            logger.warning("voice_audio_unreadable", exc_info=True)
            return None

    async def put(self, key: str, audio: bytes, ttl_seconds: int) -> bool:
        if self._redis is None:
            return False
        try:
            await self._redis.set(self._name(key), audio, ex=ttl_seconds)
        except Exception:
            logger.warning("voice_audio_not_saved", exc_info=True)
            return False
        return True


class InMemoryAudioStore:
    """For tests, and a process that has no Redis."""

    def __init__(self) -> None:
        self.clips: dict[str, bytes] = {}

    async def get(self, key: str) -> bytes | None:
        return self.clips.get(key)

    async def put(self, key: str, audio: bytes, ttl_seconds: int) -> bool:
        self.clips[key] = audio
        return True


def audio_key(text: str, *, voice: str, secret: str) -> str:
    """The clip's key and URL path segment: an HMAC, so no one can guess one."""
    return hmac.new(secret.encode(), f"{voice}\n{text}".encode(), hashlib.sha256).hexdigest()


def build_speech_synthesizer(settings: Any) -> OpenAISpeechSynthesizer | None:
    """The configured voice, or None for Unifonic's own."""
    if not settings.voice_tts_base_url:
        return None
    return OpenAISpeechSynthesizer(
        base_url=settings.voice_tts_base_url,
        model=settings.voice_tts_model,
        voice=settings.voice_tts_voice,
        api_key=settings.voice_tts_api_key,
        language=settings.voice_tts_language,
        instructions=settings.voice_tts_instructions,
        sample_rate=settings.voice_tts_sample_rate,
        timeout_seconds=settings.voice_tts_timeout_seconds,
    )


__all__ = [
    "AudioStore",
    "InMemoryAudioStore",
    "OpenAISpeechSynthesizer",
    "RedisAudioStore",
    "SpeechSynthesizer",
    "audio_key",
    "build_speech_synthesizer",
    "wav_problem",
]
