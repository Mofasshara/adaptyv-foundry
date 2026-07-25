import pytest

from adaptyv.errors import AnomalyNotAcknowledgedError, InvalidTransitionError
from adaptyv.governance.approval import ApprovalStore
from adaptyv.governance.audit import AuditLog
from adaptyv.governance.db import connect
from adaptyv.governance.models import Actor, AnomalyFinding
from evals.guards import (guard_all_numbers_grounded, guard_critical_anomalies_match,
                          guard_critical_draft_blocks_approval, guard_expected_facts_present,
                          guard_no_leftover_placeholder_syntax)

HUMAN = Actor(kind="human", id="alice")
AGENT = Actor(kind="agent", id="watcher")


def test_no_leftover_placeholder_passes_on_clean_body():
    assert guard_no_leftover_placeholder_syntax("All good, no tokens here.") == []


def test_no_leftover_placeholder_flags_a_stray_token():
    violations = guard_no_leftover_placeholder_syntax("Kd was {{kd_mean_x}}.")
    assert violations and "kd_mean_x" in violations[0]


def test_all_numbers_grounded_passes_when_number_traces_to_fact_sheet():
    fact_sheet = {"kd_mean_binder-1": "1.20e-09 M"}
    assert guard_all_numbers_grounded("Kd was 1.20e-09 M.", fact_sheet) == []


def test_all_numbers_grounded_flags_an_ungrounded_number():
    violations = guard_all_numbers_grounded("Kd was 9.99e-09 M.", {"kd_mean_binder-1": "1.20e-09 M"})
    assert violations and "9.99e-09" in violations[0]


def test_all_numbers_grounded_rejects_substring_false_negative():
    # fact_sheet contains an unusual 3-digit-exponent value "1.20e-091" whose text
    # contains "1.20e-09" as a raw substring. A body citing the shorter, different
    # number "1.20e-09" must NOT be considered grounded against it: substring
    # containment is not the same as the number actually appearing in the fact sheet.
    fact_sheet = {"kd_mean_a": "1.20e-091 M"}
    violations = guard_all_numbers_grounded("Kd was 1.20e-09 M.", fact_sheet)
    assert violations and "1.20e-09" in violations[0]


def test_critical_anomalies_match_passes_on_exact_match():
    findings = [AnomalyFinding(rule="all_sequences_failed", severity="critical", evidence="e")]
    assert guard_critical_anomalies_match(findings, frozenset({"all_sequences_failed"})) == []


def test_critical_anomalies_match_flags_missing_and_extra():
    findings = [AnomalyFinding(rule="control_out_of_policy", severity="critical", evidence="e")]
    violations = guard_critical_anomalies_match(findings, frozenset({"all_sequences_failed"}))
    assert any("all_sequences_failed" in v for v in violations)
    assert any("control_out_of_policy" in v for v in violations)


def test_expected_facts_present_passes_and_fails_correctly():
    assert guard_expected_facts_present({"kd_mean_x": "v"}, frozenset({"kd_mean_x"})) == []
    violations = guard_expected_facts_present({}, frozenset({"kd_mean_x"}))
    assert violations and "kd_mean_x" in violations[0]


def _store():
    conn = connect()
    return ApprovalStore(conn, AuditLog(conn))


def test_critical_draft_blocks_approval_passes_when_hard_block_holds():
    store = _store()
    finding = AnomalyFinding(rule="all_sequences_failed", severity="critical", evidence="e")
    draft = store.create_draft("exp-1", "body", anomalies=[finding], created_by=AGENT)
    assert guard_critical_draft_blocks_approval(store, draft.draft_id, HUMAN, is_critical=True) == []


def test_critical_draft_blocks_approval_flags_a_broken_hard_block():
    store = _store()
    draft = store.create_draft("exp-1", "body", anomalies=[], created_by=AGENT)
    # is_critical=True but no critical anomaly was actually attached -> approve()
    # will succeed, and the guard must flag that mismatch.
    violations = guard_critical_draft_blocks_approval(store, draft.draft_id, HUMAN, is_critical=True)
    assert violations


def test_critical_draft_blocks_approval_is_safe_to_call_twice_on_mismatch():
    # Reproduces the bug: on the mismatch path (is_critical=True asserted, but no
    # critical anomaly actually attached) approve() SUCCEEDS on the first call, so
    # the draft is genuinely APPROVED afterward. A second call to the guard for the
    # same draft_id must not attempt approve() again (which would raise
    # InvalidTransitionError uncaught) -- it must return [] instead, since nothing
    # new can be checked once the draft has already been resolved.
    store = _store()
    draft = store.create_draft("exp-1", "body", anomalies=[], created_by=AGENT)

    first = guard_critical_draft_blocks_approval(store, draft.draft_id, HUMAN, is_critical=True)
    assert first  # mismatch flagged on the first call

    second = guard_critical_draft_blocks_approval(store, draft.draft_id, HUMAN, is_critical=True)
    assert second == []


def test_guard_no_leftover_placeholder_syntax_catches_malformed_construct():
    from evals.guards import guard_no_leftover_placeholder_syntax
    violations = guard_no_leftover_placeholder_syntax("Kd was {{bad token}}.")
    assert violations
