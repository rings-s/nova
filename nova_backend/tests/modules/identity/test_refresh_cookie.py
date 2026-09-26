"""A browser's refresh token lives in an httpOnly cookie, never in page script.

Needs Postgres. The web app used to keep the 30-day refresh token in
localStorage, where anything injected into a page could read it and use it
from anywhere for a month. Signed in with `refresh_cookie`, the token is only
ever a cookie that script cannot read, sent only to `/api/v1/auth`.
"""

from uuid import uuid4

from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.passwords import hash_password
from app.modules.identity.auth_router import REFRESH_COOKIE
from app.modules.identity.models import User
from tests.modules.identity.test_token_revocation import authenticating_client

__all__ = ["authenticating_client"]  # the fixture, re-exported for pytest

PASSWORD = "a-long-enough-password"


async def _account(db_session: AsyncSession) -> User:
    user = User(
        email=f"cookie-{uuid4().hex[:8]}@example.com",
        full_name="Noura",
        password_hash=hash_password(PASSWORD),
    )
    db_session.add(user)
    await db_session.flush()
    return user


async def _login(client: AsyncClient, user: User, **extra: object) -> Response:
    response = await client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": PASSWORD, **extra}
    )
    assert response.status_code == 200, response.text
    return response


def _set_cookie(response: Response) -> str:
    [header] = [
        value for value in response.headers.get_list("set-cookie") if value.startswith("nova_")
    ]
    return header


async def test_a_browser_sign_in_sets_the_refresh_token_as_an_httponly_cookie(
    authenticating_client: AsyncClient, db_session: AsyncSession
):
    user = await _account(db_session)

    response = await _login(authenticating_client, user, refresh_cookie=True)

    assert response.json()["refresh_token"] is None
    assert response.json()["access_token"]
    cookie = _set_cookie(response).lower()
    assert cookie.startswith(f"{REFRESH_COOKIE}=")
    assert "httponly" in cookie
    assert "samesite=strict" in cookie
    assert "path=/api/v1/auth" in cookie
    assert "max-age=2592000" in cookie


async def test_refresh_with_no_token_uses_the_cookie_and_replaces_it(
    authenticating_client: AsyncClient, db_session: AsyncSession
):
    user = await _account(db_session)
    await _login(authenticating_client, user, refresh_cookie=True)

    refreshed = await authenticating_client.post("/api/v1/auth/refresh", json={})

    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["refresh_token"] is None
    assert refreshed.json()["access_token"]
    assert _set_cookie(refreshed).startswith(f"{REFRESH_COOKIE}=")
    token = refreshed.json()["access_token"]
    tenants = await authenticating_client.get(
        "/api/v1/tenants", headers={"Authorization": f"Bearer {token}"}
    )
    assert tenants.status_code == 200


async def test_refresh_with_neither_a_token_nor_a_cookie_is_refused(
    authenticating_client: AsyncClient,
):
    refused = await authenticating_client.post("/api/v1/auth/refresh", json={})

    assert refused.status_code == 401
    assert refused.json()["error"]["code"] == "unauthenticated"


async def test_logout_deletes_the_cookie_so_it_refreshes_nothing(
    authenticating_client: AsyncClient, db_session: AsyncSession
):
    user = await _account(db_session)
    await _login(authenticating_client, user, refresh_cookie=True)

    logged_out = await authenticating_client.post("/api/v1/auth/logout")

    assert logged_out.status_code == 204
    assert "max-age=0" in _set_cookie(logged_out).lower()
    refused = await authenticating_client.post("/api/v1/auth/refresh", json={})
    assert refused.status_code == 401


async def test_a_revoked_cookie_is_refused_like_a_revoked_token(
    authenticating_client: AsyncClient, db_session: AsyncSession
):
    user = await _account(db_session)
    await _login(authenticating_client, user, refresh_cookie=True)
    stolen = authenticating_client.cookies.get(REFRESH_COOKIE)
    assert stolen

    user.token_version += 1  # what logout-everywhere does
    await db_session.flush()
    authenticating_client.cookies.set(REFRESH_COOKIE, stolen, path="/api/v1/auth")

    refused = await authenticating_client.post("/api/v1/auth/refresh", json={})
    assert refused.status_code == 401


async def test_api_clients_still_get_and_send_the_refresh_token_in_the_body(
    authenticating_client: AsyncClient, db_session: AsyncSession
):
    user = await _account(db_session)

    signed_in = await _login(authenticating_client, user)

    assert signed_in.json()["refresh_token"]
    assert not signed_in.headers.get_list("set-cookie")
    refreshed = await authenticating_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": signed_in.json()["refresh_token"]}
    )
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["refresh_token"]
    assert not refreshed.headers.get_list("set-cookie")
