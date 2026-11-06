"""Sara's voice within a caller's turn (`SaraVoice`). No database, no network."""

import time

from app.integrations.voice.speech import InMemoryAudioStore
from app.integrations.voice.unifonic import VoiceReply
from app.modules.call_center.service import SaraVoice

SECRET = "s" * 40


class Voice:
    identity = "fake-ksa"

    def __init__(self) -> None:
        self.timeouts: list[float | None] = []

    async def synthesize(
        self, text: str, *, locale: str, timeout_seconds: float | None = None
    ) -> bytes | None:
        self.timeouts.append(timeout_seconds)
        return b"RIFF-" + text.encode()


def _sara(voice: Voice, store: InMemoryAudioStore | None = None) -> SaraVoice:
    return SaraVoice(voice, store or InMemoryAudioStore(), secret_key=SECRET, ttl_seconds=60)


async def test_speech_gets_what_the_model_left_of_the_turn():
    voice = Voice()
    spoken = await _sara(voice).speak(
        VoiceReply("حياكم الله", "ar"), base_url="http://x", deadline=time.monotonic() + 2.0
    )
    assert spoken.audio_url is not None
    [timeout] = voice.timeouts
    assert timeout is not None and 1.5 < timeout <= 2.0


async def test_with_no_time_left_unifonic_reads_the_text_at_once():
    voice = Voice()
    spoken = await _sara(voice).speak(
        VoiceReply("حياكم الله", "ar"), base_url="http://x", deadline=time.monotonic() + 0.1
    )
    assert spoken.audio_url is None
    assert voice.timeouts == [], "the voice is not even asked"


async def test_a_clip_already_made_is_played_whatever_the_time():
    voice, store = Voice(), InMemoryAudioStore()
    first = await _sara(voice, store).speak(VoiceReply("حياكم الله", "ar"), base_url="http://x")
    late = await _sara(voice, store).speak(
        VoiceReply("حياكم الله", "ar"), base_url="http://x", deadline=time.monotonic() - 1
    )
    assert late.audio_url == first.audio_url
    assert voice.timeouts == [None], "made once, with no deadline: a reminder call"
