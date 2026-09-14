"""identity · DELIVERY layer — authentication endpoints.

Unauthenticated by design (that is the point of logging in), so these carry the
tightest rate limits in the system.
"""

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db_session
from app.core.security import Principal, get_principal
from app.core.throttling import (
    client_ip_key,
    login_rate_limit,
    refresh_rate_limit,
    write_rate_limit,
)
from app.modules.identity.auth_service import AuthService, InvalidCredentialsError
from app.modules.identity.dependencies import get_auth_service
from app.modules.identity.schemas import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenOut,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])


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
    user = await service.register(
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
        phone=payload.phone,
    )
    await session.commit()
    return UserOut(id=str(user.id), email=user.email, full_name=user.full_name)


@router.post("/login", response_model=TokenOut, dependencies=[Depends(login_rate_limit)])
async def login(
    payload: LoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    service: AuthService = Depends(get_auth_service),
) -> TokenOut:
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
    return TokenOut(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        token_type=tokens.token_type,
        expires_in=tokens.expires_in,
    )


@router.post("/refresh", response_model=TokenOut, dependencies=[Depends(refresh_rate_limit)])
async def refresh(
    payload: RefreshRequest,
    service: AuthService = Depends(get_auth_service),
) -> TokenOut:
    tokens = await service.refresh(payload.refresh_token)
    return TokenOut(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        token_type=tokens.token_type,
        expires_in=tokens.expires_in,
    )


@router.post(
    "/logout-everywhere",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(write_rate_limit)],
)
async def logout_everywhere(
    session: AsyncSession = Depends(get_db_session),
    service: AuthService = Depends(get_auth_service),
    principal: Principal = Depends(get_principal),
) -> None:
    """Revokes every outstanding token for the caller.

    Bumps `token_version`, so refresh tokens are rejected immediately. Access
    tokens already issued remain valid until they expire — at most 15 minutes,
    the cost of stateless auth.
    """
    await service.revoke_all_tokens(principal.subject_id)
    await session.commit()
