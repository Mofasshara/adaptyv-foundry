import pytest

from adaptyv.errors import AnomalyNotAcknowledgedError, SelfApprovalError
from adaptyv.governance.approval import ApprovalStore
from adaptyv.governance.audit import AuditLog
from adaptyv.governance.db import connect
from adaptyv.governance.models import Actor, AnomalyFinding, DraftStatus

AGENT = Actor(kind="agent", id="watcher")
HUMAN = Actor(kind="human", id="alice")
CRIT = AnomalyFinding(rule="all_failed", severity="critical", evidence="0/3 expressed")
WARN = AnomalyFinding(rule="kd_bounds", severity="warning", evidence="Kd high")


def _store():
    conn = connect()
    return ApprovalStore(conn, AuditLog(conn))


def test_critical_anomaly_blocks_approval():
    s = _store()
    d = s.create_draft("EXP-1", "body", anomalies=[CRIT], created_by=AGENT)
    with pytest.raises(AnomalyNotAcknowledgedError):
        s.approve(d.draft_id, HUMAN)


def test_acknowledge_then_approve_succeeds_and_audits():
    s = _store()
    d = s.create_draft("EXP-1", "body", anomalies=[CRIT], created_by=AGENT)
    ack = s.acknowledge_anomaly(d.draft_id, HUMAN)
    assert ack.anomalies_acknowledged is True and ack.acknowledged_by.id == "alice"
    out = s.approve(d.draft_id, HUMAN)
    assert out.status is DraftStatus.APPROVED
    actions = [e.action for e in s._audit.entries()]
    assert "anomaly.acknowledge" in actions and actions[-1] == "draft.approve"


def test_warning_only_does_not_block():
    s = _store()
    d = s.create_draft("EXP-1", "body", anomalies=[WARN], created_by=AGENT)
    assert s.approve(d.draft_id, HUMAN).status is DraftStatus.APPROVED


def test_agent_cannot_acknowledge():
    s = _store()
    d = s.create_draft("EXP-1", "body", anomalies=[CRIT], created_by=AGENT)
    with pytest.raises(SelfApprovalError):
        s.acknowledge_anomaly(d.draft_id, AGENT)
