from pathlib import Path

from typer.testing import CliRunner

from adaptyv.cli import app
from adaptyv.governance.approval import ApprovalStore
from adaptyv.governance.audit import AuditLog
from adaptyv.governance.db import connect
from adaptyv.governance.models import Actor, AnomalyFinding

runner = CliRunner()
CRIT = AnomalyFinding(rule="all_failed", severity="critical", evidence="0/3 expressed")


def _seed(db: str) -> str:
    conn = connect(db)
    store = ApprovalStore(conn, AuditLog(conn))
    d = store.create_draft("EXP-1", "Your results are ready.", anomalies=[CRIT],
                           created_by=Actor(kind="agent", id="watcher"))
    conn.close()
    return d.draft_id


def test_review_list_and_blocked_then_ack_then_approve(tmp_path):
    db = str(tmp_path / "gov.db")
    did = _seed(db)

    r = runner.invoke(app, ["review", "list", "--db", db])
    assert r.exit_code == 0 and did[:8] in r.stdout and "pending_review" in r.stdout

    # approval blocked by critical anomaly
    r = runner.invoke(app, ["review", "approve", did, "--by", "alice", "--db", db])
    assert r.exit_code == 1 and "anomaly" in r.stdout.lower()

    # acknowledge, then approve succeeds
    assert runner.invoke(app, ["review", "ack", did, "--by", "alice", "--db", db]).exit_code == 0
    r = runner.invoke(app, ["review", "approve", did, "--by", "alice", "--db", db])
    assert r.exit_code == 0 and "approved" in r.stdout.lower()


def test_audit_list_and_verify(tmp_path):
    db = str(tmp_path / "gov.db")
    _seed(db)
    r = runner.invoke(app, ["audit", "list", "--db", db])
    assert r.exit_code == 0 and "draft.create" in r.stdout
    r = runner.invoke(app, ["audit", "verify", "--db", db])
    assert r.exit_code == 0 and "ok" in r.stdout.lower()
