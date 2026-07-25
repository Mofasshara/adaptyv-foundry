import pytest

from adaptyv.errors import AnomalyNotAcknowledgedError, InvalidTransitionError
from adaptyv.governance.approval import ApprovalStore
from adaptyv.governance.audit import AuditLog
from adaptyv.governance.db import connect
from adaptyv.governance.models import Actor, AnomalyFinding
from evals.guards import (guard_critical_anomalies_match, guard_critical_draft_blocks_approval,
                          guard_expected_facts_present)

HUMAN = Actor(kind="human", id="alice")
AGENT = Actor(kind="agent", id="watcher")

# No leftover-placeholder / all-numbers-grounded guard tests here: those
# checks now live solely inside EmailDrafter.draft() (adaptyv/agents/email.py),
# which is the single enforcement point -- see tests/test_email_drafter.py.


def test_critical_anomalies_match_passes_on_exact_match():
    findings = [AnomalyFinding(rule="all_sequences_failed", severity="critical", evidence="e")]
    assert guard_critical_anomalies_match(findings, frozenset({"all_sequences_failed"})) == []


def test_critical_anomalies_match_flags_missing_and_extra():
    findings = [AnomalyFinding(rule="control_out_of_policy", severity="critical", evidence="e")]
    violations = guard_critical_anomalies_match(findings, frozenset({"all_sequences_failed"}))
    assert any("all_sequences_failed" in v for v in violations)
    assert any("control_out_of_policy" in v for v in violations)


def test_expected_facts_present_passes_and_fails_correctly():
    assert guard_expected_facts_present({"kd_1": "v"}, frozenset({"kd_1"})) == []
    violations = guard_expected_facts_present({}, frozenset({"kd_1"}))
    assert violations and "kd_1" in violations[0]


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
