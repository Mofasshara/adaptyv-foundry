import json
import subprocess
import sys

import pytest

from adaptyv.bridge import handle_request


def test_unknown_op_returns_structured_error():
    resp = handle_request({"op": "not_a_real_op", "params": {}})
    assert resp["ok"] is False
    assert resp["error"]["type"] == "BridgeError"


def test_list_experiments_mock_default():
    resp = handle_request({"op": "list_experiments", "params": {}})
    assert resp["ok"] is True
    codes = {e["code"] for e in resp["result"]}
    assert "EXP-1001" in codes


def test_get_experiment_status():
    resp = handle_request({"op": "get_experiment_status",
                           "params": {"experiment_id": "11111111-1111-1111-1111-111111111111"}})
    assert resp["ok"] is True
    assert resp["result"]["code"] == "EXP-1001"


def test_get_experiment_status_unknown_id_maps_to_adaptyv_error():
    resp = handle_request({"op": "get_experiment_status",
                           "params": {"experiment_id": "00000000-0000-0000-0000-0000000000ff"}})
    assert resp["ok"] is False
    assert resp["error"]["type"] == "NotFoundError"


def test_get_results():
    resp = handle_request({"op": "get_results",
                           "params": {"experiment_id": "11111111-1111-1111-1111-111111111111"}})
    assert resp["ok"] is True
    assert resp["result"][0]["summary"][0]["result_type"] == "affinity"


_TARGET_ID = "44444444-0000-0000-0000-000000000001"


def test_create_experiment_with_sequences():
    resp = handle_request({"op": "create_experiment_with_sequences", "params": {
        "name": "MCP test run", "experiment_type": "affinity", "method": "bli",
        "target_id": _TARGET_ID,
        "sequences": [{"aa_string": "MKAA", "name": "binder-x"}]}})
    assert resp["ok"] is True
    assert resp["result"]["experiment_id"]


def test_create_experiment_with_sequences_missing_required_method_is_rejected():
    # affinity requires `method` -- this must be rejected, not silently
    # accepted the way a real live API call would also reject it.
    resp = handle_request({"op": "create_experiment_with_sequences", "params": {
        "name": "MCP test run", "experiment_type": "affinity", "target_id": _TARGET_ID,
        "sequences": [{"aa_string": "MKAA", "name": "binder-x"}]}})
    assert resp["ok"] is False


def test_create_experiment_bridge_op_sends_sequences_as_dict_keyed_by_name():
    from adaptyv.bridge import handle_request
    response = handle_request({
        "op": "create_experiment_with_sequences",
        "params": {
            "name": "My run",
            "experiment_type": "affinity",
            "method": "bli",
            "target_id": _TARGET_ID,
            "sequences": [{"aa_string": "MKAA", "name": "binder-1"},
                         {"aa_string": "MKZZ"}],
        },
    })
    assert response["ok"] is True


def test_search_targets():
    resp = handle_request({"op": "search_targets", "params": {"search": "IL"}})
    assert resp["ok"] is True and resp["result"]


def test_estimate_cost():
    resp = handle_request({"op": "estimate_cost", "params": {
        "experiment_type": "affinity", "method": "bli", "target_id": _TARGET_ID,
        "sequences": [{"aa_string": "MKAA"}]}})
    assert resp["ok"] is True


def test_estimate_cost_missing_required_target_id_is_rejected():
    resp = handle_request({"op": "estimate_cost", "params": {
        "experiment_type": "affinity", "method": "bli",
        "sequences": [{"aa_string": "MKAA"}]}})
    assert resp["ok"] is False


def test_add_sequences():
    resp = handle_request({"op": "add_sequences", "params": {
        "experiment_code": "EXP-1001", "sequences": [{"aa_string": "MKAA"}]}})
    assert resp["ok"] is True and resp["result"]["added_count"] == 1


def test_draft_customer_update_uses_stub_drafter_by_default(tmp_path):
    resp = handle_request({"op": "draft_customer_update", "params": {
        "experiment_id": "11111111-1111-1111-1111-111111111111",
        "db": str(tmp_path / "gov.db")}})
    assert resp["ok"] is True
    assert resp["result"]["status"] == "pending_review"


def test_missing_required_param_is_a_structured_bridge_error():
    resp = handle_request({"op": "get_experiment_status", "params": {}})
    assert resp["ok"] is False
    assert resp["error"]["type"] == "BridgeError"


def test_unexpected_exception_is_caught_as_ok_false_not_raised():
    # A real, non-contrived unexpected exception: sqlite3.OperationalError
    # from an unwritable/nonexistent db directory (exactly what a relative
    # default db path resolving to the wrong cwd could trigger). This type
    # is not one of the specifically-handled excepts (AdaptyvError, KeyError,
    # TypeError, ValueError), so it must be caught by the catch-all clause.
    resp = handle_request({"op": "draft_customer_update", "params": {
        "experiment_id": "11111111-1111-1111-1111-111111111111",
        "db": "/no_such_dir_xyz_123/gov.db"}})
    assert resp["ok"] is False
    assert resp["error"]["type"] == "OperationalError"
    assert "unable to open database file" in resp["error"]["message"]


def test_cli_entrypoint_end_to_end():
    proc = subprocess.run(
        [sys.executable, "-m", "adaptyv", "--json"],
        input=json.dumps({"op": "list_experiments", "params": {}}),
        capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0
    resp = json.loads(proc.stdout)
    assert resp["ok"] is True and resp["result"]


def test_cli_entrypoint_never_crashes_on_unexpected_exception():
    # Same unexpected-exception scenario as above, but through the full CLI
    # entrypoint: proves __main__.main() never lets an uncaught exception
    # produce a nonzero exit code or a bare traceback, even for error types
    # handle_request's specific excepts don't name.
    proc = subprocess.run(
        [sys.executable, "-m", "adaptyv", "--json"],
        input=json.dumps({"op": "draft_customer_update", "params": {
            "experiment_id": "11111111-1111-1111-1111-111111111111",
            "db": "/no_such_dir_xyz_123/gov.db"}}),
        capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0
    resp = json.loads(proc.stdout)
    assert resp["ok"] is False
    assert resp["error"]["type"] == "OperationalError"


def test_sequences_by_name_rejects_duplicate_explicit_names():
    from adaptyv.bridge import _sequences_by_name, BridgeError
    with pytest.raises(BridgeError):
        _sequences_by_name([{"aa_string": "AAA", "name": "dup"}, {"aa_string": "BBB", "name": "dup"}])


def test_sequences_by_name_rejects_unnamed_collision_with_generated_key():
    # First sequence has no name -> generated key "seq1". Second sequence is
    # explicitly named "seq1" -> collides with the generated key.
    from adaptyv.bridge import _sequences_by_name, BridgeError
    with pytest.raises(BridgeError):
        _sequences_by_name([{"aa_string": "AAA"}, {"aa_string": "BBB", "name": "seq1"}])


def test_create_experiment_bridge_op_rejects_duplicate_sequence_names():
    response = handle_request({
        "op": "create_experiment_with_sequences",
        "params": {
            "name": "My run", "experiment_type": "affinity", "method": "bli",
            "sequences": [{"aa_string": "AAA", "name": "dup"}, {"aa_string": "BBB", "name": "dup"}],
        },
    })
    assert response["ok"] is False
    assert response["error"]["type"] == "BridgeError"
