"""Unifonic Voice adapter: the phone line Sara answers (ADR-0017).

Infrastructure only: Unifonic's JSON shapes and its HTTP API. It knows nothing
about bookings or agents. `modules/call_center` decides what Sara says; this
file says it in Unifonic's words, and swapping gateways means another class
satisfying `VoiceGateway`.

How Unifonic runs a call (its "Managing your Inbound Calls" and "Making an
Outbound Call to Collect Response" guides):

- **Inbound.** A number's inbound application calls a URL we host and does
  whatever the JSON answer says: `say` text (Arabic or English, a male or
  female voice) or `play` an uploaded recording, then, with a `responseUrl`,
  listen for the caller's answer.
- **Each answer** is POSTed to that `responseUrl`: what the caller said as
  recognised text (with a `confidence`), the keys they pressed (`digits`),
  `recipient` and `callerId`. The reply to that POST is the next instruction,
  so a whole call is a loop of webhook turns. No media stream is involved.
- **`responseUrl` takes no Authorization header.** The URL itself is the
  credential, which is why `call_center` signs every one it hands out.
- **Outbound** calls are placed through the API with the first instruction,
  and their answers come back to a `responseUrl` the same way.
- **Sara's own voice.** With a speech server configured (`speech.py`), a reply
  is a recording we host, which `play` names by URL; otherwise `say` has
  Unifonic read the text in its own Arabic voice.

Unifonic's docs sit behind a login, so the field names below come from its
public guides and are checked in one place each. To verify on a live account
before go-live: the inbound request's field names, the recognised-speech
field, the outbound endpoint and its auth, and how long Unifonic waits for a
reply (`VOICE_AI_REQUEST_TIMEOUT_SECONDS` must stay under it), and whether
`play` takes an audio URL rather than only an uploaded recording's id.
"""

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.core.exceptions import DomainError
from app.integrations.base import IntegrationNotConfiguredError

logger = logging.getLogger(__name__)


class VoiceGatewayError(DomainError):
    """Unifonic refused a call or could not be reached. Its own message is logged.

    `may_have_placed` is True when the request reached Unifonic and the answer
    was lost (a read timeout, a 5xx): the phone may be ringing, so trying again
    could ring it twice. It is False only when the call certainly was not
    placed: no connection was made, or Unifonic refused it with a 4xx.
    """

    status_code = 502
    code = "voice_gateway_error"

    def __init__(
        self,
        message: str = "The phone provider could not place the call.",
        may_have_placed: bool = False,
    ) -> None:
        super().__init__(message)
        self.may_have_placed = may_have_placed
        self.retryable = not may_have_placed


@dataclass(frozen=True)
class VoiceReply:
    """One thing Sara says, then, with `listen_url`, the caller's turn.

    Without `listen_url` the call ends once she has spoken. With `audio_url`
    (her own voice, `speech.py`) the clip is played; without it, Unifonic's
    text-to-speech reads `say`.
    """

    say: str
    locale: str
    listen_url: str | None = None
    audio_url: str | None = None


@dataclass(frozen=True)
class IncomingCall:
    gateway_call_id: str | None
    caller: str | None
    recipient: str | None


@dataclass(frozen=True)
class CallerInput:
    """One answer from the caller: words Unifonic recognised, keys pressed, or neither."""

    gateway_call_id: str | None
    text: str
    digits: str
    confidence: float | None


class VoiceGateway(Protocol):
    """Operations NOVA needs from the phone provider."""

    def render(self, reply: VoiceReply) -> dict[str, Any]:
        """The JSON answer to a webhook that makes the provider say `reply`."""
        ...

    def parse_incoming(self, params: Mapping[str, Any]) -> IncomingCall: ...

    def parse_answer(self, payload: Mapping[str, Any]) -> CallerInput: ...

    async def place_call(self, *, to: str, caller_id: str, reply: VoiceReply) -> str:
        """Dials `to` from `caller_id` and says `reply`. Returns the provider's call id."""
        ...


_LANGUAGES = {"ar": "arabic", "en": "english"}
#: Sara is a woman's name; she speaks with the female voice.
_VOICE = "female"

#: Where the caller's number and the call's id may arrive, first match wins.
_CALLER_FIELDS = ("callerId", "caller_id", "from", "From")
_RECIPIENT_FIELDS = ("recipient", "to", "To", "calledNumber")
_CALL_ID_FIELDS = ("callSid", "call_sid", "callId", "call_id", "CallSid")
#: The recognised speech. Not named in the public guides; to verify.
_SPEECH_FIELDS = ("speech", "speechResult", "speechText", "transcript", "text", "response")
#: What a phone's keypad can send.
_KEYS = frozenset("0123456789*#")


#: Errors raised before the request reached Unifonic: no call can have been placed.
_NEVER_SENT = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.PoolTimeout,
    httpx.UnsupportedProtocol,
)


def _first(source: Mapping[str, Any], names: tuple[str, ...]) -> str | None:
    for name in names:
        value = source.get(name)
        if value not in (None, ""):
            return str(value)
    return None


class UnifonicVoiceFormat:
    """Unifonic's instruction and webhook shapes. Pure: no network, no credentials."""

    def render(self, reply: VoiceReply) -> dict[str, Any]:
        language = _LANGUAGES.get(reply.locale[:2], "arabic")
        instruction: dict[str, Any]
        if reply.audio_url is not None:
            # Sara's own voice. The public guide shows `play` with an uploaded
            # recording's id; a URL in its place is to verify on a live account.
            instruction = {"play": reply.audio_url}
        else:
            instruction = {"say": reply.say, "language": language, "voice": _VOICE}
        if reply.listen_url is not None:
            instruction["responseUrl"] = reply.listen_url
            instruction["speechCollectionLanguage"] = language
            instruction["loop"] = 1
        return instruction

    def parse_incoming(self, params: Mapping[str, Any]) -> IncomingCall:
        return IncomingCall(
            gateway_call_id=_first(params, _CALL_ID_FIELDS),
            caller=_first(params, _CALLER_FIELDS),
            recipient=_first(params, _RECIPIENT_FIELDS),
        )

    def parse_answer(self, payload: Mapping[str, Any]) -> CallerInput:
        confidence = payload.get("confidence")
        try:
            score = float(confidence) if confidence is not None else None
        except (TypeError, ValueError):
            score = None
        digits = _first(payload, ("digits", "Digits")) or ""
        return CallerInput(
            gateway_call_id=_first(payload, _CALL_ID_FIELDS),
            text=(_first(payload, _SPEECH_FIELDS) or "").strip(),
            # Keys only: anything else in the field is not something a phone sends.
            # Not `str.isdigit`, which also passes Arabic-Indic digits and "²".
            digits="".join(c for c in digits if c in _KEYS),
            confidence=score,
        )


class NotConfiguredVoiceGateway(UnifonicVoiceFormat):
    """Answers Unifonic's webhooks, which need no credentials, but places no call."""

    async def place_call(self, *, to: str, caller_id: str, reply: VoiceReply) -> str:
        raise IntegrationNotConfiguredError("Unifonic Voice")


class UnifonicVoiceGateway(UnifonicVoiceFormat):
    """Live adapter: outbound calls through the Unifonic Voice API."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://voice.unifonic.com/v1",
        timeout_seconds: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        #: For tests: an `httpx.MockTransport` in place of the network.
        self.transport = transport

    async def place_call(self, *, to: str, caller_id: str, reply: VoiceReply) -> str:
        """`POST /calls`. Never retried here: a retry after a timeout could ring twice.

        Raises `VoiceGatewayError`, whose `may_have_placed` tells a caller
        whether trying again later is safe.
        """
        body = {"recipient": to, "callerId": caller_id, **self.render(reply)}
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout_seconds,
                headers={"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"},
                transport=self.transport,
            ) as client:
                response = await client.post("/calls", json=body)
        except httpx.HTTPError as exc:
            logger.warning("unifonic_voice_unreachable", extra={"error": repr(exc)})
            # Only a request that never left can be sent again without a doubt.
            raise VoiceGatewayError(may_have_placed=not isinstance(exc, _NEVER_SENT)) from exc
        if not response.is_success:
            logger.error(
                "unifonic_voice_error",
                extra={"status": response.status_code, "body": response.text[:500]},
            )
            raise VoiceGatewayError(may_have_placed=response.status_code >= 500)
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        call_id = _first(data, _CALL_ID_FIELDS)
        if call_id is None:
            raise VoiceGatewayError(
                "The phone provider accepted the call but returned no id.", may_have_placed=True
            )
        return call_id


def build_voice_gateway(*, api_key: str | None, base_url: str) -> VoiceGateway:
    """Picks the live adapter or the placeholder, based on configuration."""
    if not api_key:
        return NotConfiguredVoiceGateway()
    return UnifonicVoiceGateway(api_key=api_key, base_url=base_url)


__all__ = [
    "CallerInput",
    "IncomingCall",
    "NotConfiguredVoiceGateway",
    "UnifonicVoiceGateway",
    "VoiceGateway",
    "VoiceGatewayError",
    "VoiceReply",
    "build_voice_gateway",
]
