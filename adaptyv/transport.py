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
        self._sequence_detail = load_fixture("sequence_detail.json")

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
        m = re.fullmatch(r"/api/v1/sequences/([^/]+)", path)
        if method == "GET" and m:
            return self._detail(self._sequences, m.group(1),
                                 full=self._sequence_detail, kind="sequence")
        for coll, kind in ((self._targets, "target"), (self._results, "result")):
            m = re.fullmatch(rf"/api/v1/{kind}s/([^/]+)", path)
            if method == "GET" and m:
                return self._detail(coll, m.group(1), kind=kind)
        if method == "POST" and path == "/api/v1/experiments":
            return {"experiment_id": "99999999-9999-9999-9999-999999999999"}
        m = re.fullmatch(r"/api/v1/experiments/([^/]+)/submit", path)
        if method == "POST" and m:
            return {"experiment_id": m.group(1), "previous_status": "draft", "status": "quote_sent",
                    "confirmed_at": "2026-07-24T00:00:00Z"}
        if method == "POST" and path == "/api/v1/experiments/cost-estimate":
            return {"breakdown": {
                "pricing_version": "v1_2026-01-20",
                "assay": {"experiment_type": "affinity", "sequence_count": 1, "n_replicates": 3,
                          "unit_price_cents": 15000, "replicate_price_cents": 5000,
                          "subtotal_cents": 25000},
                "total_cents": 25000,
            }, "warnings": []}
        if method == "POST" and path == "/api/v1/sequences":
            body = json or {}
            return {"experiment_id": "11111111-1111-1111-1111-111111111111",
                    "experiment_code": body.get("experiment_code", "EXP-1001"),
                    "added_count": len(body.get("sequences", [])),
                    "sequence_ids": ["33333333-0000-0000-0000-0000000000aa"]}
        raise NotFoundError(f"MockTransport has no route for {method} {path}", status_code=404)

    def _detail(self, items, item_id, *, full=None, kind="item"):
        for it in items:
            if it["id"] == item_id:
                return full if (full and full.get("id") == item_id) else it
        raise NotFoundError(f"{kind} {item_id} not found", status_code=404)
