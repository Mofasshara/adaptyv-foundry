import httpx
import pytest
import respx
from adaptyv.errors import AuthError, NotFoundError, TransportError
from adaptyv.live_transport import LiveTransport

BASE = "https://devs.adaptyvbio.com"


def _lt(**kw):
    return LiveTransport(base_url=BASE, api_key="secret", sleep=lambda *_: None, **kw)


@respx.mock
def test_get_sends_bearer_and_parses_envelope():
    r = respx.get(f"{BASE}/api/v1/experiments").mock(
        return_value=httpx.Response(200, json={"items": [], "total": 0, "count": 0, "offset": 0})
    )
    assert _lt().request("GET", "/api/v1/experiments")["total"] == 0
    assert r.calls.last.request.headers["authorization"] == "Bearer secret"


@respx.mock
def test_error_body_uses_error_field_and_maps_type():
    respx.get(f"{BASE}/api/v1/x").mock(
        return_value=httpx.Response(
            404,
            json={
                "error": "experiment not found",
                "request_id": "55555555-5555-5555-5555-555555555555",
            },
        )
    )
    with pytest.raises(NotFoundError) as ei:
        _lt().request("GET", "/api/v1/x")
    assert "experiment not found" in str(ei.value)


@respx.mock
def test_retries_get_on_429_then_succeeds_exactly_twice():
    route = respx.get(f"{BASE}/api/v1/results").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "0"}, json={"error": "slow", "request_id": "x"}),
            httpx.Response(200, json={"items": [], "total": 0, "count": 0, "offset": 0}),
        ]
    )
    _lt(max_retries=2).request("GET", "/api/v1/results")
    assert route.call_count == 2


@respx.mock
def test_post_is_not_retried():
    route = respx.post(f"{BASE}/api/v1/experiments").mock(
        return_value=httpx.Response(503, json={"error": "down", "request_id": "x"})
    )
    with pytest.raises(TransportError):
        _lt(max_retries=2).request("POST", "/api/v1/experiments", json={})
    assert route.call_count == 1


def test_missing_key_raises_auth():
    with pytest.raises(AuthError):
        LiveTransport(base_url=BASE, api_key=None).request("GET", "/api/v1/experiments")


@respx.mock
def test_retries_get_on_non_numeric_retry_after_then_succeeds():
    sleeps: list[float] = []
    route = respx.get(f"{BASE}/api/v1/results").mock(
        side_effect=[
            httpx.Response(
                429,
                headers={"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"},
                json={"error": "slow", "request_id": "x"},
            ),
            httpx.Response(200, json={"items": [], "total": 0, "count": 0, "offset": 0}),
        ]
    )
    lt = LiveTransport(base_url=BASE, api_key="secret", sleep=sleeps.append, max_retries=2)
    lt.request("GET", "/api/v1/results")
    assert route.call_count == 2
    assert sleeps == [0.2]


def test_close_and_context_manager_close_underlying_client():
    lt = _lt()
    lt.close()
    assert lt._http.is_closed

    with _lt() as ctx_lt:
        assert not ctx_lt._http.is_closed
    assert ctx_lt._http.is_closed
