"""The Unifonic Voice adapter: its JSON shapes and the outbound call. No network."""

import json

import httpx
import pytest

from app.integrations.base import IntegrationNotConfiguredError
from app.integrations.voice.unifonic import (
    NotConfiguredVoiceGateway,
    UnifonicVoiceGateway,
    VoiceGatewayError,
    VoiceReply,
    build_voice_gateway,
)


def test_a_reply_says_then_listens_in_sara_s_voice():
    rendered = NotConfiguredVoiceGateway().render(
        VoiceReply("أهلًا", "ar", "https://api.example.sa/next")
    )
    assert rendered == {
        "say": "أهلًا",
        "language": "arabic",
        "voice": "female",
        "responseUrl": "https://api.example.sa/next",
        "speechCollectionLanguage": "arabic",
        "loop": 1,
    }


def test_a_last_reply_does_not_listen():
    rendered = NotConfiguredVoiceGateway().render(VoiceReply("Goodbye.", "en"))
    assert rendered == {"say": "Goodbye.", "language": "english", "voice": "female"}


def test_an_answer_reads_speech_keys_and_confidence():
    answer = NotConfiguredVoiceGateway().parse_answer(
        {"speech": "  ابي موعد  ", "digits": "1<script>", "confidence": "0.8", "callSid": "c-1"}
    )
    assert answer.text == "ابي موعد"
    assert answer.digits == "1", "only what a keypad can send"
    assert answer.confidence == 0.8
    assert answer.gateway_call_id == "c-1"
    # `str.isdigit` would keep both: neither is a key on a phone.
    assert NotConfiguredVoiceGateway().parse_answer({"digits": "\u0661²3#"}).digits == "3#"


def test_an_incoming_call_names_the_caller_and_the_line():
    incoming = NotConfiguredVoiceGateway().parse_incoming(
        {"callerId": "+966500000001", "recipient": "+966800123456", "callSid": "c-9"}
    )
    assert incoming.caller == "+966500000001"
    assert incoming.recipient == "+966800123456"
    assert incoming.gateway_call_id == "c-9"


async def test_without_a_key_no_call_is_placed():
    gateway = build_voice_gateway(api_key=None, base_url="https://voice.example")
    with pytest.raises(IntegrationNotConfiguredError):
        await gateway.place_call(
            to="+966500000001", caller_id="+966800123456", reply=VoiceReply("x", "ar")
        )


async def test_an_outbound_call_sends_the_first_reply_and_returns_the_call_id():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"data": {"callSid": "out-1"}})

    gateway = UnifonicVoiceGateway(
        api_key="key", base_url="https://voice.example/v1", transport=httpx.MockTransport(handler)
    )
    call_id = await gateway.place_call(
        to="+966500000001",
        caller_id="+966800123456",
        reply=VoiceReply("تذكير", "ar", "https://api.example.sa/next"),
    )

    assert call_id == "out-1"
    [request] = seen
    assert request.url == "https://voice.example/v1/calls"
    assert request.headers["Authorization"] == "Bearer key"
    body = json.loads(request.content)
    assert body["recipient"] == "+966500000001"
    assert body["callerId"] == "+966800123456"
    assert body["responseUrl"] == "https://api.example.sa/next"


async def test_a_refused_call_raises_a_retryable_gateway_error():
    gateway = UnifonicVoiceGateway(
        api_key="key",
        base_url="https://voice.example/v1",
        transport=httpx.MockTransport(lambda request: httpx.Response(401, json={})),
    )
    with pytest.raises(VoiceGatewayError) as raised:
        await gateway.place_call(
            to="+966500000001", caller_id="+966800123456", reply=VoiceReply("x", "ar")
        )
    assert raised.value.retryable
    assert not raised.value.may_have_placed


def _failing(handler) -> UnifonicVoiceGateway:
    return UnifonicVoiceGateway(
        api_key="key", base_url="https://voice.example/v1", transport=httpx.MockTransport(handler)
    )


@pytest.mark.parametrize(
    ("handler", "may_have_placed"),
    [
        (lambda r: (_ for _ in ()).throw(httpx.ConnectError("refused", request=r)), False),
        (lambda r: (_ for _ in ()).throw(httpx.ConnectTimeout("slow", request=r)), False),
        (lambda r: httpx.Response(422, json={}), False),
        # Unifonic had the request: the phone may be ringing.
        (lambda r: (_ for _ in ()).throw(httpx.ReadTimeout("slow", request=r)), True),
        (lambda r: httpx.Response(503, json={}), True),
        (lambda r: httpx.Response(200, json={}), True),
    ],
)
async def test_a_failed_call_says_whether_the_phone_may_be_ringing(handler, may_have_placed):
    with pytest.raises(VoiceGatewayError) as raised:
        await _failing(handler).place_call(
            to="+966500000001", caller_id="+966800123456", reply=VoiceReply("x", "ar")
        )
    assert raised.value.may_have_placed is may_have_placed
    assert raised.value.retryable is not may_have_placed, "a retry could ring twice"


def test_a_reply_in_sara_s_own_voice_is_played_from_its_url():
    rendered = NotConfiguredVoiceGateway().render(
        VoiceReply(
            "أبشروا",
            "ar",
            "https://api.example.sa/next",
            audio_url="https://api.example.sa/api/v1/webhooks/voice/audio/abc.wav",
        )
    )
    assert rendered["play"] == "https://api.example.sa/api/v1/webhooks/voice/audio/abc.wav"
    assert "say" not in rendered
    assert rendered["responseUrl"] == "https://api.example.sa/next"
