"""Tests for the settings rules that stop an unsafe deployment from starting.

Pure — no database. Each test builds `Settings` with `_env_file=None` and names
every field its answer depends on, so the environment the suite runs in (the
compose stack sets ENV, SECRET_KEY and AUTH_DEV_BYPASS) cannot change it.
"""

import pathlib

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
        "client_ip_header": "CF-Connecting-IP",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


class TestEnvironmentDefault:
    def test_an_unset_env_means_production(self, monkeypatch):
        """A deployment that forgets ENV must get the strict rules, not local's."""
        for name in ("ENV", "AUTH_DEV_BYPASS", "CLOUDFLARE_TUNNEL_TOKEN"):
            monkeypatch.delenv(name, raising=False)

        settings = Settings(
            _env_file=None, **REQUIRED, secret_key=GENERATED_KEY, client_ip_header="X-Real-IP"
        )

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


class TestClientIpHeader:
    def test_no_header_is_trusted_by_default(self):
        assert build(env="local", client_ip_header=None).trusted_client_ip_header is None

    @pytest.mark.parametrize("env", ["staging", "production"])
    def test_a_deployed_process_refuses_to_start_without_one(self, env):
        """Else every client is the proxy's address, or one it forged (docs/14 TM-02)."""
        with pytest.raises(ValidationError, match="Set CLIENT_IP_HEADER"):
            build(env=env, client_ip_header=None)

    def test_the_runtime_image_does_not_trust_forwarded_headers(self):
        """`--forwarded-allow-ips "*"` makes X-Forwarded-For the client address."""
        dockerfile = pathlib.Path(__file__).resolve().parents[1] / "Dockerfile"
        code = [ln for ln in dockerfile.read_text().splitlines() if not ln.lstrip().startswith("#")]
        assert not any("--forwarded-allow-ips" in ln or "--proxy-headers" in ln for ln in code)

    def test_cloudflares_header_is_trusted_behind_the_tunnel(self):
        settings = build(client_ip_header=None, cloudflare_tunnel_token="token")
        assert settings.trusted_client_ip_header == "CF-Connecting-IP"

    def test_a_configured_header_wins(self):
        settings = build(client_ip_header="X-Real-IP", cloudflare_tunnel_token="token")
        assert settings.trusted_client_ip_header == "X-Real-IP"

    @pytest.mark.parametrize("header", ["X-Forwarded-For", " x-forwarded-for "])
    def test_x_forwarded_for_is_refused(self, header):
        """Its first entry is whatever the client sent: the bypass this closes."""
        with pytest.raises(ValidationError, match="cannot be X-Forwarded-For"):
            build(client_ip_header=header)


class TestMoyasarKey:
    """A key of the wrong kind fails every payment at its first request, so
    the process refuses to start on one instead."""

    def test_the_publishable_key_is_refused(self):
        with pytest.raises(ValidationError, match="secret key"):
            build(env="local", moyasar_api_key="pk_test_abc")

    def test_a_test_key_is_refused_in_production(self):
        with pytest.raises(ValidationError, match="test key in production"):
            build(moyasar_api_key="sk_test_abc")

    @pytest.mark.parametrize(("env", "key"), [("local", "sk_test_a"), ("staging", "sk_test_a")])
    def test_a_test_key_is_fine_before_production(self, env, key):
        assert build(env=env, moyasar_api_key=key).moyasar_api_key == key

    def test_a_live_key_is_fine_in_production(self):
        assert build(moyasar_api_key="sk_live_a").moyasar_api_key == "sk_live_a"

    def test_no_key_at_all_is_fine(self):
        assert build(moyasar_api_key=None).moyasar_api_key is None


class TestMoyasarPublishableKey:
    """The browser's key: public, but it has to match the secret key's mode,
    and it must never be the secret key itself."""

    def test_the_secret_key_is_refused(self):
        with pytest.raises(ValidationError, match="publishable key"):
            build(env="local", moyasar_publishable_key="sk_test_abc")

    def test_a_test_key_is_refused_in_production(self):
        with pytest.raises(ValidationError, match="test key in production"):
            build(moyasar_api_key="sk_live_a", moyasar_publishable_key="pk_test_abc")

    @pytest.mark.parametrize(
        ("secret", "publishable"), [("sk_test_a", "pk_live_a"), ("sk_live_a", "pk_test_a")]
    )
    def test_the_two_keys_must_share_a_mode(self, secret, publishable):
        with pytest.raises(ValidationError, match="both be test keys"):
            build(env="staging", moyasar_api_key=secret, moyasar_publishable_key=publishable)

    @pytest.mark.parametrize(
        ("env", "secret", "publishable"),
        [("local", "sk_test_a", "pk_test_a"), ("production", "sk_live_a", "pk_live_a")],
    )
    def test_a_matching_pair_is_fine(self, env, secret, publishable):
        settings = build(env=env, moyasar_api_key=secret, moyasar_publishable_key=publishable)
        assert settings.moyasar_publishable_key == publishable

    def test_no_key_at_all_is_fine(self):
        assert build(moyasar_publishable_key=None).moyasar_publishable_key is None


class TestMoyasarKeyNames:
    @pytest.mark.parametrize("name", ["MOYASAR_SECRET_KEY_ID", "MOYASAR_API_KEY"])
    def test_the_secret_key_is_read_from_either_name(self, monkeypatch, name):
        for other in ("MOYASAR_SECRET_KEY_ID", "MOYASAR_API_KEY"):
            monkeypatch.delenv(other, raising=False)
        monkeypatch.setenv(name, "sk_test_abc")

        settings = Settings(_env_file=None, **REQUIRED, secret_key=GENERATED_KEY, env="local")

        assert settings.moyasar_api_key == "sk_test_abc"
