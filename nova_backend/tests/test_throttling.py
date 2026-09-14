"""Which address an IP rate limit charges a request to. Pure — no database, no Redis.

A limit keyed on something the client writes is not a limit. This one was keyed
on X-Forwarded-For, and a new value on every request defeated the login limiter.
"""

from types import SimpleNamespace

import pytest
from starlette.requests import Request

from app.core import throttling
from app.core.throttling import client_ip_key


def make_request(peer: str | None, headers: dict[str, str] | None = None) -> Request:
    raw_headers = [
        (name.lower().encode(), value.encode()) for name, value in (headers or {}).items()
    ]
    return Request(
        {"type": "http", "headers": raw_headers, "client": (peer, 50000) if peer else None}
    )


@pytest.fixture
def trust(monkeypatch):
    """Sets the header `Settings.trusted_client_ip_header` names. None to begin with."""

    def _trust(header: str | None) -> None:
        settings = SimpleNamespace(trusted_client_ip_header=header)
        monkeypatch.setattr(throttling, "get_settings", lambda: settings)

    _trust(None)
    return _trust


def test_x_forwarded_for_is_never_read(trust):
    request = make_request("203.0.113.9", {"X-Forwarded-For": "198.51.100.1"})
    assert client_ip_key(request) == "203.0.113.9"


def test_x_forwarded_for_is_not_read_behind_a_trusted_proxy_either(trust):
    trust("CF-Connecting-IP")
    request = make_request("203.0.113.9", {"X-Forwarded-For": "198.51.100.1"})
    assert client_ip_key(request) == "203.0.113.9"


def test_the_trusted_header_names_the_client(trust):
    trust("CF-Connecting-IP")
    request = make_request("172.19.0.5", {"CF-Connecting-IP": "198.51.100.7"})
    assert client_ip_key(request) == "198.51.100.7"


def test_the_header_is_ignored_until_it_is_trusted(trust):
    request = make_request("172.19.0.5", {"CF-Connecting-IP": "198.51.100.7"})
    assert client_ip_key(request) == "172.19.0.5"


def test_a_malformed_trusted_header_falls_back_to_the_peer(trust):
    trust("CF-Connecting-IP")
    request = make_request("172.19.0.5", {"CF-Connecting-IP": "198.51.100.7, 203.0.113.1"})
    assert client_ip_key(request) == "172.19.0.5"


def test_ipv6_is_charged_by_its_64(trust):
    first = make_request("2001:db8:1:2:aaaa::1")
    second = make_request("2001:db8:1:2:bbbb::2")
    assert client_ip_key(first) == client_ip_key(second) == "2001:db8:1:2::/64"


def test_an_ipv4_mapped_peer_counts_as_ipv4(trust):
    assert client_ip_key(make_request("::ffff:203.0.113.9")) == "203.0.113.9"


def test_a_request_with_no_address_shares_one_bucket(trust):
    assert client_ip_key(make_request(None)) == "unknown"
