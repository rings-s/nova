"""Tests for the settings rules that stop an unsafe deployment from starting.

Pure — no database. Each test builds `Settings` with `_env_file=None` and names
every field its answer depends on, so the environment the suite runs in (the
compose stack sets ENV, SECRET_KEY and AUTH_DEV_BYPASS) cannot change it.
"""

import pytest
from pydantic import ValidationError

from app.core.config import Settings

#: The shape `openssl rand -hex 32` produces.
GENERATED_KEY = "3f" * 32

REQUIRED = {
    "database_url": "postgresql+asyncpg://nova_app:pw@localhost:5432/nova",
    "redis_url": "redis://localhost:6379/0",
}


def build(**overrides: object) -> Settings:
    values: dict[str, object] = {
        **REQUIRED,
        "secret_key": GENERATED_KEY,
        "env": "production",
        "auth_dev_bypass": False,
        "cloudflare_tunnel_token": None,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


class TestEnvironmentDefault:
    def test_an_unset_env_means_production(self, monkeypatch):
        """A deployment that forgets ENV must get the strict rules, not local's."""
        for name in ("ENV", "AUTH_DEV_BYPASS", "CLOUDFLARE_TUNNEL_TOKEN"):
            monkeypatch.delenv(name, raising=False)

        settings = Settings(_env_file=None, **REQUIRED, secret_key=GENERATED_KEY)

        assert settings.env == "production"


class TestSecretKey:
    def test_accepts_a_generated_key_in_production(self):
        assert build().secret_key == GENERATED_KEY

    @pytest.mark.parametrize("env", ["local", "test", "staging", "production"])
    def test_refuses_an_empty_key_everywhere(self, env):
        with pytest.raises(ValidationError, match="SECRET_KEY is empty"):
            build(env=env, secret_key="")

    @pytest.mark.parametrize("env", ["staging", "production"])
    def test_refuses_a_short_key_when_deployed(self, env):
        with pytest.raises(ValidationError, match="too weak"):
            build(env=env, secret_key="a" * 31)

    def test_refuses_the_placeholder_the_example_file_used_to_ship(self):
        """Long enough, and still public: it was committed to the repository."""
        with pytest.raises(ValidationError, match="too weak"):
            build(secret_key="change-me-to-a-random-value-" + "x" * 10)

    @pytest.mark.parametrize("env", ["local", "test"])
    def test_a_developer_may_use_a_short_key(self, env):
        assert build(env=env, secret_key="dev").secret_key == "dev"


class TestDevBypass:
    @pytest.mark.parametrize("env", ["local", "test"])
    def test_allowed_on_a_developer_machine(self, env):
        assert build(env=env, auth_dev_bypass=True).auth_dev_bypass

    @pytest.mark.parametrize("env", ["staging", "production"])
    def test_refused_when_deployed(self, env):
        with pytest.raises(ValidationError, match="honoured only in local or test"):
            build(env=env, auth_dev_bypass=True)

    def test_refused_on_a_stack_a_tunnel_publishes(self):
        """`make tunnel` would otherwise put an API that needs no token online."""
        with pytest.raises(ValidationError, match="CLOUDFLARE_TUNNEL_TOKEN"):
            build(env="local", auth_dev_bypass=True, cloudflare_tunnel_token="token")
