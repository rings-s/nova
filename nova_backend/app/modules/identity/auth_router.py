"""identity · DELIVERY layer — authentication endpoints.

Unauthenticated by design (that is the point of logging in), so these carry the
tightest rate limits in the system.
"""

from typing import Any

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import get_db_session
from app.core.security import (
    REFRESH_TOKEN_TTL_SECONDS,
    AuthenticationError,
    Principal,
    get_principal,
)
from app.core.throttling import (
    client_ip_key,
    login_rate_limit,
    refresh_rate_limit,
    write_rate_limit,
)
from app.modules.identity.auth_service import AuthService, InvalidCredentialsError, TokenPair
from app.modules.identity.dependencies import get_auth_service
from app.modules.identity.schemas import (
    ConfirmPhoneVerificationRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenOut,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])

#: The browser's refresh token, when it signed in with `refresh_cookie`.
#: httpOnly, so page script, and anything injected into the page, cannot read
#: it. Sent only to these routes, and only from the same site (SameSite=Strict),
#: which also keeps another site from spending it.
REFRESH_COOKIE = "nova_refresh"
_REFRESH_COOKIE_PATH = "/api/v1/auth"


def _cookie_options() -> dict[str, Any]:
    # A test client, or a dev server reached over plain http, drops a Secure
    # cookie; everywhere else it must be Secure.
    secure = get_settings().env not in {"local", "test"}
    return {"path": _REFRESH_COOKIE_PATH, "httponly": True, "secure": secure, "samesite": "strict"}


def _token_out(tokens: TokenPair, response: Response, *, as_cookie: bool) -> TokenOut:
    """The pair, with the refresh token either in the body or in the cookie, never both."""
    if as_cookie:
        response.set_cookie(
            REFRESH_COOKIE,
            tokens.refresh_token,
            max_age=REFRESH_TOKEN_TTL_SECONDS,
            **_cookie_options(),
        )
    return TokenOut(
        access_token=tokens.access_token,
        refresh_token=None if as_cookie else tokens.refresh_token,
        token_type=tokens.token_type,
        expires_in=tokens.expires_in,
    )


@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(login_rate_limit)],
)
async def register(
    payload: RegisterRequest,
    session: AsyncSession = Depends(get_db_session),
    service: AuthService = Depends(get_auth_service),
) -> UserOut:
    """Creates an account. It does not sign you in: call `POST /auth/login` next.

    Passwords are at least 12 characters. A new account is a customer; creating a
    business (`POST /tenants`) makes you its owner. Booking needs a phone number on
    the account."""
    user = await service.register(
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
        phone=payload.phone,
    )
    await session.commit()
    return UserOut(id=str(user.id), email=user.email, full_name=user.full_name)


@router.get("/me", response_model=UserOut)
async def me(
    service: AuthService = Depends(get_auth_service),
    principal: Principal = Depends(get_principal),
) -> UserOut:
    """The signed-in account: who it is, and whether it is a NOVA administrator."""
    user = await service.get_account(principal)
    return UserOut(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        is_superuser=user.is_superuser,
    )


@router.post("/login", response_model=TokenOut, dependencies=[Depends(login_rate_limit)])
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db_session),
    service: AuthService = Depends(get_auth_service),
) -> TokenOut:
    """Signs in, returning an access token (15 minutes) and a refresh token (30 days).

    Send the access token as `Authorization: Bearer <token>`. With `refresh_cookie`,
    the refresh token is set as an httpOnly cookie instead of returned: what a
    browser should ask for. Every refusal answers 401 `invalid_credentials`,
    whether the password was wrong or repeated failures have locked the account
    for a while."""
    try:
        tokens = await service.login(
            email=payload.email, password=payload.password, client_key=client_ip_key(request)
        )
    except InvalidCredentialsError:
        # A failed attempt's count, and any lock it triggers, must outlive the
        # error. Without this commit they rolled back with it, and no account
        # ever locked however many passwords were tried.
        await session.commit()
        raise
    await session.commit()
    return _token_out(tokens, response, as_cookie=payload.refresh_cookie)


@router.post("/refresh", response_model=TokenOut, dependencies=[Depends(refresh_rate_limit)])
async def refresh(
    payload: RefreshRequest,
    request: Request,
    response: Response,
    service: AuthService = Depends(get_auth_service),
) -> TokenOut:
    """Exchanges a refresh token for a new access and refresh token.

    Send the refresh token in the body, or send none to use the refresh cookie;
    the new one then replaces the cookie and is not returned. Call it when a
    request answers 401. The new access token carries your current memberships,
    so refresh after creating a business or accepting an invite to reach it.
    Refused after `POST /auth/logout-everywhere`."""
    from_cookie = payload.refresh_token is None
    token = request.cookies.get(REFRESH_COOKIE) if from_cookie else payload.refresh_token
    if not token:
        raise AuthenticationError("No refresh token. Sign in again.")
    tokens = await service.refresh(token)
    return _token_out(tokens, response, as_cookie=from_cookie)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(refresh_rate_limit)],
)
async def logout(response: Response) -> None:
    """Signs this browser out: deletes the refresh cookie, which page script cannot.

    Tokens already issued stay valid until they expire (the access token within
    15 minutes). To end every one, on every device, use
    `POST /auth/logout-everywhere`."""
    response.delete_cookie(REFRESH_COOKIE, **_cookie_options())


@router.post(
    "/logout-everywhere",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(write_rate_limit)],
)
async def logout_everywhere(
    response: Response,
    session: AsyncSession = Depends(get_db_session),
    service: AuthService = Depends(get_auth_service),
    principal: Principal = Depends(get_principal),
) -> None:
    """Revokes every outstanding token for the caller.

    Bumps `token_version`. Every token already issued, access and refresh, is
    refused from its next use: `get_principal` compares the version on every
    request, and refresh does too.
    """
    await service.revoke_all_tokens(principal.subject_id)
    await session.commit()
    response.delete_cookie(REFRESH_COOKIE, **_cookie_options())


@router.post(
    "/phone/verify/request",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(write_rate_limit)],
)
async def request_phone_verification(
    session: AsyncSession = Depends(get_db_session),
    service: AuthService = Depends(get_auth_service),
    principal: Principal = Depends(get_principal),
) -> None:
    """Sends a short-lived, purpose-signed JWT to the account's own phone over
    WhatsApp (docs/14 TM-01).

    Proving the number is what lets a later self-service booking claim an
    existing, unclaimed customer record that phone matches — see
    `CustomerService.ensure_for_user`.
    """
    await service.request_phone_verification(principal.subject_id)
    await session.commit()


@router.post(
    "/phone/verify/confirm",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(write_rate_limit)],
)
async def confirm_phone_verification(
    payload: ConfirmPhoneVerificationRequest,
    session: AsyncSession = Depends(get_db_session),
    service: AuthService = Depends(get_auth_service),
    principal: Principal = Depends(get_principal),
) -> None:
    """Proves the account's phone number with the token that
    `POST /auth/phone/verify/request` sent over WhatsApp.

    Once proven, a booking at a salon that already has you on record under that
    number links to that record instead of being refused."""
    await service.confirm_phone_verification(principal.subject_id, payload.token)
    await session.commit()
