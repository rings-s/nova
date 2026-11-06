"""call_center · DELIVERY layer — Unifonic's webhooks, the call log, the lines.

The webhooks are public: Unifonic sends no Authorization header. Each URL is
signed instead (`CallCenterService`), and the tenant in the path is the one the
signature names, so the connection is scoped to it before anything is read.
They are the voice channel's equivalent of `POST /webhooks/moyasar`.
"""

import json
import time
from datetime import UTC, datetime
from typing import Annotated
from urllib.parse import parse_qsl
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import get_db_session
from app.core.exceptions import DomainError
from app.core.throttling import write_rate_limit
from app.db.session import set_tenant_scope
from app.modules.ai_agents.exceptions import AiBusyError
from app.modules.call_center.dependencies import (
    VoiceCallServices,
    get_call_center_service,
    get_sara_voice,
)
from app.modules.call_center.domain import Call
from app.modules.call_center.exceptions import AudioNotFoundError
from app.modules.call_center.schemas import (
    CallOut,
    CreatePhoneLineRequest,
    PhoneLineOut,
    PhoneLineSetupOut,
)
from app.modules.call_center.service import CallCenterService, LineSetup, SaraVoice
from app.modules.identity.dependencies import RequirePermission, require_superuser
from app.modules.identity.domain import StaffPermission

webhook_router = APIRouter(prefix="/webhooks/voice", tags=["call_center"])


def _base_url(request: Request) -> str:
    """Where Unifonic reaches this API: configured, or the origin it just used."""
    return get_settings().voice_public_base_url or str(request.base_url)


def _deadline() -> float:
    """When this turn's answer must be ready (`VOICE_TURN_BUDGET_SECONDS`)."""
    return time.monotonic() + get_settings().voice_turn_budget_seconds


def _payload(raw: bytes) -> dict:
    """A webhook body as a dict, JSON or form-encoded; anything else is empty."""
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        try:
            return dict(parse_qsl(raw.decode(), keep_blank_values=True))
        except UnicodeDecodeError:
            return {}
    return value if isinstance(value, dict) else {}


@webhook_router.get("/{tenant_id}/lines/{line_token}")
async def answer_call(
    tenant_id: UUID,
    line_token: str,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    voice: Annotated[VoiceCallServices, Depends()],
) -> dict:
    """Unifonic's inbound application: a call to one of the tenant's lines rings.

    Sara greets the caller and starts the call, or, at a business whose plan
    does not include her, says the business cannot take calls. A forged or
    revoked line URL answers 404 `phone_line_not_found`.
    """
    deadline = _deadline()
    await set_tenant_scope(session, tenant_id)
    service = voice.build(session, tenant_id)
    base_url = _base_url(request)
    reply = await service.answer(
        line_token, dict(request.query_params), base_url=base_url, now=datetime.now(UTC)
    )
    await session.commit()
    spoken = await service.speak(reply, base_url=base_url, deadline=deadline)
    return service.gateway.render(spoken)


@webhook_router.post("/{tenant_id}/calls/{call_token}")
async def caller_turn(
    tenant_id: UUID,
    call_token: str,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    voice: Annotated[VoiceCallServices, Depends()],
) -> dict:
    """The caller's answer: what they said, or the keys they pressed.

    The answer to this request is what Sara says next. Keys are handled here,
    never by the model: 1 books the time Sara is holding, 2 cancels a booking
    Sara offered to cancel, and a 4-digit code proves the caller holds the
    customer's phone. The model runs with no transaction open: the call row is
    committed before and updated after. A retried delivery gets the same
    answer without running the model again. The model and Sara's voice share
    one `VOICE_TURN_BUDGET_SECONDS`: speech that would not be ready in time is
    left to Unifonic's voice. A forged or expired link answers 404
    `call_not_found`.
    """
    deadline = _deadline()
    service = voice.build(session, tenant_id)
    call_id = service.call_id_from(call_token)
    raw = await request.body()
    base_url = _base_url(request)

    await set_tenant_scope(session, tenant_id)
    plan = await service.begin_answer(
        call_id, _payload(raw), raw, base_url=base_url, now=datetime.now(UTC)
    )
    await session.commit()
    if plan.reply is not None:
        spoken = await service.speak(plan.reply, base_url=base_url, deadline=deadline)
        return service.gateway.render(spoken)

    try:
        turn = await service.converse(plan)
    except (AiBusyError, DomainError):
        # Busy, or the plan locked mid-call: ask again rather than drop the call.
        turn = None

    await set_tenant_scope(session, tenant_id)
    reply = await service.finish_answer(plan, turn, base_url=base_url, now=datetime.now(UTC))
    await session.commit()
    # The model has had its share of the turn; speech gets what is left.
    spoken = await service.speak(reply, base_url=base_url, deadline=deadline)
    return service.gateway.render(spoken)


@webhook_router.get(
    "/audio/{key}.wav",
    response_class=Response,
    responses={200: {"content": {"audio/wav": {}}}},
)
async def sara_audio(key: str, voice: Annotated[SaraVoice, Depends(get_sara_voice)]) -> Response:
    """One of Sara's replies as audio, for Unifonic to play (ADR-0017).

    The key is an HMAC of the voice and the words, so a clip cannot be found
    without the link Sara's reply carried. Clips expire after
    `VOICE_TTS_CACHE_SECONDS`; an unknown or expired one answers 404
    `audio_not_found`. Reads no database and no tenant.
    """
    audio = await voice.clip(key)
    if audio is None:
        raise AudioNotFoundError()
    return Response(content=audio, media_type="audio/wav")


router = APIRouter(prefix="/tenants/{tenant_id}/call-center", tags=["call_center"])


def _call_out(call: Call) -> CallOut:
    return CallOut(
        id=call.id,
        line_id=call.line_id,
        business_id=call.business_id,
        direction=str(call.direction),
        purpose=str(call.purpose),
        status=str(call.status),
        outcome=str(call.outcome) if call.outcome else None,
        caller_e164=call.caller_e164,
        customer_id=call.customer_id,
        booking_id=call.booking_id,
        turns=call.turns,
        verified=call.verified,
        started_at=call.started_at,
        ended_at=call.ended_at,
    )


def _setup_out(setup: LineSetup) -> PhoneLineSetupOut:
    return PhoneLineSetupOut(
        line=PhoneLineOut.model_validate(setup.line, from_attributes=True),
        answer_url=setup.answer_url,
    )


@router.get(
    "/calls",
    response_model=list[CallOut],
    dependencies=[Depends(RequirePermission(StaffPermission.VIEW_CUSTOMERS))],
)
async def list_calls(
    tenant_id: UUID,
    *,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    service: Annotated[CallCenterService, Depends(get_call_center_service)],
) -> list[CallOut]:
    """The business's calls with Sara, newest first: who called, and what came of it.

    Callers' numbers are customer data, so this needs `view_customers`.
    """
    return [_call_out(call) for call in await service.recent_calls(limit=limit, offset=offset)]


@router.get(
    "/lines",
    response_model=list[PhoneLineOut],
    dependencies=[Depends(require_superuser)],
)
async def list_lines(
    tenant_id: UUID,
    service: Annotated[CallCenterService, Depends(get_call_center_service)],
) -> list[PhoneLineOut]:
    """The tenant's phone lines. NOVA administrators only: NOVA buys the numbers."""
    return [
        PhoneLineOut.model_validate(line, from_attributes=True)
        for line in await service.list_lines()
    ]


@router.post(
    "/lines",
    response_model=PhoneLineSetupOut,
    status_code=201,
    dependencies=[Depends(require_superuser), Depends(write_rate_limit)],
)
async def create_line(
    tenant_id: UUID,
    payload: CreatePhoneLineRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    service: Annotated[CallCenterService, Depends(get_call_center_service)],
) -> PhoneLineSetupOut:
    """Connects a Unifonic number to one business, and returns the URL to give Unifonic.

    NOVA administrators only. `answer_url` is the line's credential and is
    shown once here (and again by `rotate`). 409 `phone_number_taken` when the
    number already rings a business.
    """
    setup = await service.provision_line(
        business_id=payload.business_id,
        number_e164=payload.number_e164,
        locale=payload.locale,
        base_url=_base_url(request),
    )
    await session.commit()
    return _setup_out(setup)


@router.post(
    "/lines/{line_id}/rotate",
    response_model=PhoneLineSetupOut,
    dependencies=[Depends(require_superuser), Depends(write_rate_limit)],
)
async def rotate_line(
    tenant_id: UUID,
    line_id: UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    service: Annotated[CallCenterService, Depends(get_call_center_service)],
) -> PhoneLineSetupOut:
    """A new answer URL for the line. The old one stops working at once."""
    setup = await service.rotate_line(line_id, base_url=_base_url(request))
    await session.commit()
    return _setup_out(setup)
