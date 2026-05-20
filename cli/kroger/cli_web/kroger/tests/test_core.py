"""Unit tests for cli-web-kroger core module.

These tests do NOT require a browser or network connection — they validate
the exception hierarchy, client construction, and raise_for_status() logic.
"""
from __future__ import annotations

import pytest

from cli_web.kroger.core.exceptions import (
    AuthError,
    KrogerError,
    NetworkError,
    NotFoundError,
    RateLimitError,
    RPCError,
    ServerError,
    raise_for_status,
)
from cli_web.kroger.core.client import KrogerClient, DEFAULT_LOCATION_ID


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_kroger_error_is_base_exception():
    assert issubclass(KrogerError, Exception)


@pytest.mark.unit
def test_not_found_error_is_kroger_error():
    assert issubclass(NotFoundError, KrogerError)


@pytest.mark.unit
def test_network_error_is_kroger_error():
    assert issubclass(NetworkError, KrogerError)


@pytest.mark.unit
def test_auth_error_is_kroger_error():
    assert issubclass(AuthError, KrogerError)


@pytest.mark.unit
def test_rate_limit_error_is_kroger_error():
    assert issubclass(RateLimitError, KrogerError)


@pytest.mark.unit
def test_server_error_is_kroger_error():
    assert issubclass(ServerError, KrogerError)


@pytest.mark.unit
def test_rpc_error_is_kroger_error():
    assert issubclass(RPCError, KrogerError)


# ---------------------------------------------------------------------------
# KrogerClient construction
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_client_default_location_id():
    client = KrogerClient()
    assert client.location_id == DEFAULT_LOCATION_ID
    assert client.location_id == "70100070"


@pytest.mark.unit
def test_client_custom_location_id():
    client = KrogerClient(location_id="12345678")
    assert client.location_id == "12345678"


@pytest.mark.unit
def test_client_has_expected_methods():
    expected = [
        "search_products",
        "get_product",
        "get_reviews",
        "get_coupons",
        "get_recommendations",
        "close",
    ]
    for method in expected:
        assert hasattr(KrogerClient, method), f"KrogerClient missing method: {method}"
        assert callable(getattr(KrogerClient, method))


# ---------------------------------------------------------------------------
# raise_for_status()
# ---------------------------------------------------------------------------


class _FakeResponse:
    """Minimal response stub for raise_for_status() tests."""

    def __init__(self, status_code: int, text: str = "", headers: dict | None = None):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}


@pytest.mark.unit
def test_raise_for_status_200_is_noop():
    # Should not raise for 2xx
    raise_for_status(_FakeResponse(200))
    raise_for_status(_FakeResponse(204))


@pytest.mark.unit
def test_raise_for_status_401_raises_auth_error():
    with pytest.raises(AuthError):
        raise_for_status(_FakeResponse(401))


@pytest.mark.unit
def test_raise_for_status_403_raises_auth_error():
    with pytest.raises(AuthError):
        raise_for_status(_FakeResponse(403))


@pytest.mark.unit
def test_raise_for_status_404_raises_not_found_error():
    with pytest.raises(NotFoundError):
        raise_for_status(_FakeResponse(404))


@pytest.mark.unit
def test_raise_for_status_429_raises_rate_limit_error():
    with pytest.raises(RateLimitError):
        raise_for_status(_FakeResponse(429))


@pytest.mark.unit
def test_raise_for_status_429_extracts_retry_after():
    response = _FakeResponse(429, headers={"Retry-After": "30"})
    with pytest.raises(RateLimitError) as exc_info:
        raise_for_status(response)
    assert exc_info.value.retry_after == 30.0


@pytest.mark.unit
def test_raise_for_status_503_raises_server_error():
    with pytest.raises(ServerError):
        raise_for_status(_FakeResponse(503))


@pytest.mark.unit
def test_raise_for_status_500_raises_server_error():
    with pytest.raises(ServerError):
        raise_for_status(_FakeResponse(500))


@pytest.mark.unit
def test_server_error_captures_status_code():
    with pytest.raises(ServerError) as exc_info:
        raise_for_status(_FakeResponse(503))
    assert exc_info.value.status_code == 503


@pytest.mark.unit
def test_raise_for_status_4xx_fallback_raises_kroger_error():
    # 410 is not mapped specifically, should raise base KrogerError
    with pytest.raises(KrogerError):
        raise_for_status(_FakeResponse(410))


# ---------------------------------------------------------------------------
# to_dict() on exceptions
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_not_found_to_dict():
    err = NotFoundError("not found")
    d = err.to_dict()
    assert d["error"] is True
    assert d["code"] == "NOT_FOUND"
    assert "not found" in d["message"]


@pytest.mark.unit
def test_rate_limit_to_dict_includes_retry_after():
    err = RateLimitError("too many requests", retry_after=60.0)
    d = err.to_dict()
    assert d["code"] == "RATE_LIMITED"
    assert d["retry_after"] == 60.0


@pytest.mark.unit
def test_rate_limit_to_dict_omits_retry_after_when_none():
    err = RateLimitError("too many requests", retry_after=None)
    d = err.to_dict()
    assert "retry_after" not in d
