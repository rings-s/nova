"""Where the API publishes its own map. Pure — no database.

`/docs`, `/redoc` and `/openapi.json` list every route and parameter. Served in
every environment, they handed that list to whoever found a deployed host.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings, get_settings
from app.main import create_app

DOC_PATHS = ("/docs", "/redoc", "/openapi.json")


def _settings(**fields: object) -> Settings:
    values: dict[str, object] = {"env": "production", "api_docs_enabled": None}
    values.update(fields)
    return Settings.model_construct(**values)


@pytest.mark.parametrize(
    ("env", "served"),
    [("local", True), ("test", True), ("staging", False), ("production", False)],
)
def test_docs_are_served_only_in_development_by_default(env: str, served: bool) -> None:
    assert _settings(env=env).serve_api_docs is served


@pytest.mark.parametrize("env", ["staging", "production"])
def test_a_deployment_may_publish_them_on_purpose(env: str) -> None:
    assert _settings(env=env, api_docs_enabled=True).serve_api_docs is True


def test_a_developer_may_switch_them_off() -> None:
    assert _settings(env="local", api_docs_enabled=False).serve_api_docs is False


@pytest.fixture
def docs_switched_off(monkeypatch: pytest.MonkeyPatch):
    get_settings.cache_clear()
    monkeypatch.setenv("API_DOCS_ENABLED", "false")
    yield
    get_settings.cache_clear()


async def test_an_app_with_docs_off_publishes_none_of_them(docs_switched_off) -> None:
    app = create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for path in DOC_PATHS:
            assert (await client.get(path)).status_code == 404, path
