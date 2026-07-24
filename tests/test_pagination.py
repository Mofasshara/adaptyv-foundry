from __future__ import annotations

import pytest

from adaptyv import AdaptyvClient
from adaptyv.errors import AdaptyvError, TransportError
from adaptyv.models import ExperimentListItem


def _item(n: int) -> dict:
    return {
        "id": f"{n:08d}-0000-0000-0000-000000000000",
        "code": f"EXP-{1000 + n}",
        "status": "done",
        "results_status": "all",
        "created_at": "2026-07-01T10:00:00Z",
        "experiment_url": f"https://devs.adaptyvbio.com/e/EXP-{1000 + n}",
        "experiment_type": "affinity",
        "name": f"Item {n}",
    }


class TwoPageTransport:
    """Stub transport that ignores the requested 'limit' and always serves a fixed
    chunk size of 2 (like a server-enforced page cap), but honors the requested
    'offset' — so the test proves _paged follows the envelope, not just the
    caller's limit."""

    def __init__(self) -> None:
        self._all = [_item(1), _item(2), _item(3)]
        self.calls: list[dict] = []

    def request(self, method: str, path: str, *, params=None, json=None):
        assert method == "GET" and path == "/api/v1/experiments"
        params = params or {}
        self.calls.append(dict(params))
        offset = params.get("offset", 0)
        page = self._all[offset:offset + 2]
        return {"items": page, "total": len(self._all), "count": len(page), "offset": offset}


class EmptyEnvelopeTransport:
    """Stub transport that returns a malformed envelope (no 'items' key)."""

    def request(self, method: str, path: str, *, params=None, json=None):
        return {}


class NotADictTransport:
    """Stub transport that returns a non-dict body."""

    def request(self, method: str, path: str, *, params=None, json=None):
        return ["not", "a", "dict"]


def test_paged_auto_paginates_across_multiple_pages():
    transport = TwoPageTransport()
    client = AdaptyvClient(transport=transport)
    exps = client.experiments.list()
    assert [e.code for e in exps] == ["EXP-1001", "EXP-1002", "EXP-1003"]
    assert all(isinstance(e, ExperimentListItem) for e in exps)
    # Proves the loop actually paged: more than one request was made.
    assert len(transport.calls) == 2
    assert transport.calls[1]["offset"] == 2


def test_paged_respects_caller_supplied_limit_and_offset_as_starting_window():
    transport = TwoPageTransport()
    client = AdaptyvClient(transport=transport)
    exps = client.experiments.list(limit=1, offset=1)
    assert transport.calls[0]["offset"] == 1
    assert transport.calls[0]["limit"] == 1
    assert [e.code for e in exps] == ["EXP-1002", "EXP-1003"]


def test_paged_raises_typed_error_on_missing_items_key():
    client = AdaptyvClient(transport=EmptyEnvelopeTransport())
    with pytest.raises(TransportError):
        client.experiments.list()


def test_paged_raises_typed_error_on_non_dict_envelope():
    client = AdaptyvClient(transport=NotADictTransport())
    with pytest.raises(AdaptyvError):
        client.experiments.list()
