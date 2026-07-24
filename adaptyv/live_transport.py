from __future__ import annotations

import time
from typing import Any, Callable

import httpx

from adaptyv.errors import AuthError, TransportError, error_for_status

_RETRY = {429, 500, 502, 503, 504}
_IDEMPOTENT = {"GET", "HEAD"}


class LiveTransport:
    def __init__(
        self,
        base_url: str,
        api_key: str | None,
        *,
        max_retries: int = 2,
        timeout: float = 30.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._key = api_key
        self._max = max_retries
        self._sleep = sleep
        self._http = httpx.Client(timeout=timeout)

    def request(self, method: str, path: str, *, params=None, json=None) -> Any:
        if not self._key and not path.startswith("/api/v1/info/health"):
            raise AuthError(
                "No API key. Pass api_key=, set ADAPTYV_API_KEY, or use mock=True.",
                status_code=401,
            )
        url = f"{self._base}{path}"
        headers = {"Authorization": f"Bearer {self._key}"} if self._key else {}
        attempts = self._max + 1 if method.upper() in _IDEMPOTENT else 1
        for i in range(attempts):
            resp = self._http.request(method, url, params=params, json=json, headers=headers)
            if resp.status_code in _RETRY and i < attempts - 1:
                default_delay = 0.2 * (i + 1)
                retry_after = resp.headers.get("Retry-After")
                try:
                    delay = float(retry_after) if retry_after is not None else default_delay
                except ValueError:
                    # Retry-After may be an HTTP-date instead of a delta-seconds value;
                    # fall back to the default backoff rather than crashing.
                    delay = default_delay
                self._sleep(delay)
                continue
            if resp.status_code >= 400:
                raise _to_error(resp)
            return resp.json() if resp.content else None
        raise TransportError("request failed after retries")

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "LiveTransport":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


def _to_error(resp: httpx.Response):
    msg, rid = f"HTTP {resp.status_code}", resp.headers.get("x-request-id")
    try:
        body = resp.json()
        msg = body.get("error", msg)
        rid = body.get("request_id", rid)
    except Exception:
        pass
    return error_for_status(resp.status_code, msg, rid)
