from __future__ import annotations
import re
from typing import Any, Protocol

from adaptyv.errors import NotFoundError
from adaptyv.mocks import load_fixture


class Transport(Protocol):
    def request(self, method: str, path: str, *, params: dict | None = None,
                json: dict | None = None) -> Any: ...


def _page(items: list[dict], offset: int = 0) -> dict:
    return {"items": items, "total": len(items), "count": len(items), "offset": offset}


class MockTransport:
    """Serves fixture data with the same shapes as the live API. This is demo mode."""

    def __init__(self) -> None:
        self._experiments = load_fixture("experiments_list.json")["items"]
        self._experiment_detail = load_fixture("experiment_detail.json")
        self._results = load_fixture("results_list.json")["items"]
        self._targets = load_fixture("targets_list.json")["items"]
        self._sequences = load_fixture("sequences_list.json")["items"]

    def request(self, method: str, path: str, *, params=None, json=None) -> Any:
        if method == "GET" and path == "/api/v1/experiments":
            return _page(self._experiments)
        if method == "GET" and path == "/api/v1/results":
            return _page(self._results)
        if method == "GET" and path == "/api/v1/targets":
            return _page(self._targets)
        if method == "GET" and path == "/api/v1/sequences":
            return _page(self._sequences)
        m = re.fullmatch(r"/api/v1/experiments/([^/]+)", path)
        if method == "GET" and m:
            return self._detail(self._experiments, m.group(1),
                                 full=self._experiment_detail, kind="experiment")
        m = re.fullmatch(r"/api/v1/experiments/([^/]+)/results", path)
        if method == "GET" and m:
            self._detail(self._experiments, m.group(1), kind="experiment")  # 404 if unknown
            return _page([r for r in self._results if r["experiment_id"] == m.group(1)])
        for coll, kind in ((self._targets, "target"), (self._results, "result"),
                           (self._sequences, "sequence")):
            m = re.fullmatch(rf"/api/v1/{kind}s/([^/]+)", path)
            if method == "GET" and m:
                return self._detail(coll, m.group(1), kind=kind)
        raise NotFoundError(f"MockTransport has no route for {method} {path}", status_code=404)

    def _detail(self, items, item_id, *, full=None, kind="item"):
        for it in items:
            if it["id"] == item_id:
                return full if (full and full.get("id") == item_id) else it
        raise NotFoundError(f"{kind} {item_id} not found", status_code=404)
