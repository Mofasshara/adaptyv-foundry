"""State-change + audit-entry atomicity for the governance store.

These tests use a FILE-BASED sqlite db so a SECOND connection can observe
whatever was actually made durable (committed) by the first connection —
in-process, same-connection reads would show uncommitted writes too, which
would hide the bug this guards against.
"""
import pytest

from adaptyv.errors import DraftNotFoundError
from adaptyv.governance.approval import ApprovalStore
from adaptyv.governance.audit import AuditLog
from adaptyv.governance.db import connect
from adaptyv.governance.models import Actor, DraftStatus

AGENT = Actor(kind="agent", id="watcher")
HUMAN = Actor(kind="human", id="alice")


def _store(db_path: str) -> ApprovalStore:
    conn = connect(db_path)
    return ApprovalStore(conn, AuditLog(conn))


def test_approve_persists_atomically_with_audit_on_reconnect(tmp_path):
    db = str(tmp_path / "gov.db")
    store = _store(db)
    d = store.create_draft("EXP-1", "body", created_by=AGENT)
    out = store.approve(d.draft_id, HUMAN)
    assert out.status is DraftStatus.APPROVED

    # A fresh connection to the same file must see the committed approval.
    reopened = _store(db)
    assert reopened.get(d.draft_id).status is DraftStatus.APPROVED
    assert reopened._audit.entries()[-1].action == "draft.approve"


def test_failed_audit_write_leaves_no_durable_state_change(tmp_path, monkeypatch):
    db = str(tmp_path / "gov.db")
    store = _store(db)
    d = store.create_draft("EXP-1", "body", created_by=AGENT)

    # Sanity: draft.create's own state+audit pair already made it durable
    # via a fresh connection before we break anything.
    reopened = _store(db)
    assert reopened.get(d.draft_id).status is DraftStatus.PENDING_REVIEW

    def _boom(*args, **kwargs):
        raise RuntimeError("audit backend unavailable")

    monkeypatch.setattr(store._audit, "record", _boom)

    with pytest.raises(RuntimeError):
        store.approve(d.draft_id, HUMAN)

    # A SECOND, independent connection to the same db file must still see
    # the draft as pending_review: the UPDATE must not have durably
    # committed without its paired audit entry.
    verifier = connect(db)
    row = verifier.execute("SELECT status FROM drafts WHERE draft_id=?", (d.draft_id,)).fetchone()
    assert row["status"] == DraftStatus.PENDING_REVIEW.value
