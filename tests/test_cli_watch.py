from typer.testing import CliRunner

from adaptyv.cli import app
from adaptyv.governance.approval import ApprovalStore
from adaptyv.governance.audit import AuditLog
from adaptyv.governance.db import connect

runner = CliRunner()


def test_watch_once_drafts_and_reports(tmp_path):
    db = str(tmp_path / "gov.db")
    result = runner.invoke(app, ["watch", "--once", "--db", db])
    assert result.exit_code == 0
    assert "drafted:" in result.stdout


def test_watch_once_is_idempotent_across_invocations(tmp_path):
    db = str(tmp_path / "gov.db")
    runner.invoke(app, ["watch", "--once", "--db", db])
    second = runner.invoke(app, ["watch", "--once", "--db", db])
    assert second.exit_code == 0
    conn = connect(db)
    store = ApprovalStore(conn, AuditLog(conn))
    first_count = len(store.list())
    runner.invoke(app, ["watch", "--once", "--db", db])
    assert len(store.list()) == first_count  # no new drafts on the third run
