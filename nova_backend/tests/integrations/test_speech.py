"""Sara's voice: the OpenAI-compatible speech request (Qwen3-TTS on vLLM-Omni). No network."""

import io
import json
import wave

import httpx
import pytest

from app.integrations.voice.speech import (
    OpenAISpeechSynthesizer,
    RedisAudioStore,
    audio_key,
    wav_problem,
)


def _wav(*, rate: int = 8000, channels: int = 1, frames: int = 80) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as clip:
        clip.setnchannels(channels)
        clip.setsampwidth(2)
        clip.setframerate(rate)
        clip.writeframes(b"\x00\x00" * channels * frames)
    return out.getvalue()


WAV = _wav()


def _voice(handler, **overrides) -> OpenAISpeechSynthesizer:
    values = {
        "base_url": "http://tts.example/v1",
        "model": "vadimbelsky/qwen3-TTS-KSA",
        "voice": "ksa_speaker",
        "transport": httpx.MockTransport(handler),
    }
    return OpenAISpeechSynthesizer(**{**values, **overrides})


async def test_an_arabic_reply_is_asked_for_in_the_saudi_voice_at_phone_quality():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=WAV, headers={"content-type": "audio/wav"})

    audio = await _voice(handler, api_key="k", instructions="Warm").synthesize(
        "حياكم الله", locale="ar"
    )

    assert audio == WAV
    [request] = seen
    assert request.url == "http://tts.example/v1/audio/speech"
    assert request.headers["Authorization"] == "Bearer k"
    assert json.loads(request.content) == {
        "model": "vadimbelsky/qwen3-TTS-KSA",
        "input": "حياكم الله",
        "voice": "ksa_speaker",
        "response_format": "wav",
        "language": "Arabic",
        "sample_rate": 8000,
        "instructions": "Warm",
    }


async def test_english_is_left_to_unifonic_because_the_saudi_voice_speaks_arabic_only():
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("no request for a language the voice does not speak")

    assert await _voice(handler).synthesize("Hello", locale="en") is None


async def test_a_failing_or_slow_server_leaves_the_text_for_unifonic():
    def refused(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="model not loaded")

    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("too slow", request=request)

    assert await _voice(refused).synthesize("حياكم الله", locale="ar") is None
    assert await _voice(slow).synthesize("حياكم الله", locale="ar") is None


def test_a_clip_key_depends_on_the_secret_the_voice_and_the_words():
    key = audio_key("حياكم الله", voice="v1", secret="s")
    assert len(key) == 64
    assert key != audio_key("حياكم الله", voice="v1", secret="other")
    assert key != audio_key("حياكم الله", voice="v2", secret="s")
    assert key != audio_key("أبشروا", voice="v1", secret="s")


class _DownRedis:
    async def get(self, name):
        raise ConnectionError("Redis is down")

    async def set(self, name, value, ex=None):
        raise ConnectionError("Redis is down")


async def test_a_store_that_could_not_keep_a_clip_says_so():
    # Sara then lets Unifonic read the text: a link to it would be a 404, and silence.
    assert await RedisAudioStore(_DownRedis()).put("k", WAV, 60) is False
    assert await RedisAudioStore(None).put("k", WAV, 60) is False
    assert await RedisAudioStore(_DownRedis()).get("k") is None


@pytest.mark.parametrize(
    ("audio", "problem"),
    [
        (_wav(), None),
        (_wav(rate=24000), "24000 Hz, not 8000"),
        (_wav(channels=2), "2 channels, not mono"),
        (_wav(frames=0), "no audio"),
        (b'{"error": "model not loaded"}', "not a PCM WAV"),
        (b"RIFF\x24\x00\x00\x00WAVEfmt ", "not a PCM WAV"),
    ],
)
def test_only_mono_pcm_at_the_phone_rate_is_phone_audio(audio: bytes, problem: str | None):
    found = wav_problem(audio, sample_rate=8000)
    assert (found is None) if problem is None else (found or "").startswith(problem)


async def test_audio_a_phone_cannot_play_is_left_to_unifonic():
    # A server that ignored `sample_rate`, or answered an error with 200.
    for body in (_wav(rate=24000), b'{"error": "busy"}'):
        voice = _voice(lambda request, body=body: httpx.Response(200, content=body))
        assert await voice.synthesize("حياكم الله", locale="ar") is None


async def test_the_turn_s_deadline_shortens_the_voice_s_timeout():
    seen: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.extensions["timeout"]["read"])
        return httpx.Response(200, content=WAV)

    voice = _voice(handler, timeout_seconds=4.0)
    await voice.synthesize("حياكم الله", locale="ar", timeout_seconds=1.5)
    await voice.synthesize("حياكم الله", locale="ar", timeout_seconds=9.0)
    await voice.synthesize("حياكم الله", locale="ar")
    assert seen == [1.5, 4.0, 4.0]
