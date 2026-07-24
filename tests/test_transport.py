import pytest
from adaptyv.errors import NotFoundError
from adaptyv.transport import MockTransport


def test_list_returns_pagination_envelope():
    env = MockTransport().request("GET", "/api/v1/experiments")
    assert set(env) >= {"items", "total", "count", "offset"}
    assert isinstance(env["items"], list) and env["items"]


def test_detail_returns_bare_object():
    t = MockTransport()
    exp_id = t.request("GET", "/api/v1/experiments")["items"][0]["id"]
    exp = t.request("GET", f"/api/v1/experiments/{exp_id}")
    assert exp["id"] == exp_id and "experiment_spec" in exp


def test_results_for_experiment_filtered():
    t = MockTransport()
    env = t.request("GET", "/api/v1/results")
    assert env["items"] and env["items"][0]["summary"][0]["result_type"] == "affinity"


def test_unknown_detail_raises():
    with pytest.raises(NotFoundError):
        MockTransport().request("GET", "/api/v1/experiments/00000000-0000-0000-0000-0000000000ff")
