from adaptyv.governance.models import (
    Actor, ActorKind, AnomalyFinding, AnomalySeverity, Draft, DraftStatus,
    has_unacknowledged_critical,
)
from adaptyv.governance.db import connect
from adaptyv.errors import AdaptyvError, GovernanceError, SelfApprovalError


def test_actor_and_enums():
    a = Actor(kind="human", id="alice")
    assert a.kind is ActorKind.HUMAN
    assert DraftStatus.PENDING_REVIEW.value == "pending_review"
    assert AnomalySeverity.CRITICAL.value == "critical"


def test_unacknowledged_critical_helper():
    crit = AnomalyFinding(rule="all_failed", severity="critical", evidence="0/3 expressed")
    warn = AnomalyFinding(rule="kd_bounds", severity="warning", evidence="Kd high")
    d = Draft(draft_id="d1", experiment_id="e1", status="pending_review", body="hi",
              anomalies=[crit], created_by=Actor(kind="agent", id="watcher"),
              created_at="2026-07-24T10:00:00Z")
    assert has_unacknowledged_critical(d) is True
    d.anomalies_acknowledged = True
    assert has_unacknowledged_critical(d) is False
    d2 = d.model_copy(update={"anomalies": [warn], "anomalies_acknowledged": False})
    assert has_unacknowledged_critical(d2) is False


def test_governance_errors_are_adaptyv_errors():
    assert issubclass(GovernanceError, AdaptyvError)
    assert issubclass(SelfApprovalError, GovernanceError)


def test_connect_returns_row_factory_conn():
    conn = connect()
    conn.execute("CREATE TABLE t (x INTEGER)")
    conn.execute("INSERT INTO t VALUES (1)")
    row = conn.execute("SELECT x FROM t").fetchone()
    assert row["x"] == 1
