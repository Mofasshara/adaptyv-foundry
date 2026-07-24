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


def test_failed_mutation_is_rolled_back_not_swept_into_a_later_commit(tmp_path, monkeypatch):
    """A failed record() must roll back its own uncommitted state write.

    Without a rollback, the failed write sits open on the shared
    connection. If that same connection/store is later reused for a
    DIFFERENT, successful mutation, that later mutation's record() commit
    durably commits BOTH writes together — silently landing the earlier
    failed operation's state change with no corresponding audit entry.
    This is the regression the atomicity fix's rollback must prevent.
    """
    db = str(tmp_path / "gov.db")
    store = _store(db)
    d1 = store.create_draft("EXP-1", "body", created_by=AGENT)
    d2 = store.create_draft("EXP-2", "body", created_by=AGENT)

    real_record = store._audit.record
    calls = {"n": 0}

    def _flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("audit backend unavailable")
        return real_record(*args, **kwargs)

    monkeypatch.setattr(store._audit, "record", _flaky)

    # First mutation: fails on its audit write.
    with pytest.raises(RuntimeError):
        store.approve(d1.draft_id, HUMAN)

    # Second, successful mutation on the SAME store/connection (record()
    # now works, since only the first call was made to raise).
    out2 = store.approve(d2.draft_id, HUMAN)
    assert out2.status is DraftStatus.APPROVED

    # Reopen the db via a fresh connection and confirm ONLY d2's approval
    # (and its audit entry) is durable.
    verifier = connect(db)

    row1 = verifier.execute("SELECT status FROM drafts WHERE draft_id=?", (d1.draft_id,)).fetchone()
    assert row1["status"] == DraftStatus.PENDING_REVIEW.value, (
        "the failed approve's state write must not have been swept into "
        "d2's later successful commit"
    )

    row2 = verifier.execute("SELECT status FROM drafts WHERE draft_id=?", (d2.draft_id,)).fetchone()
    assert row2["status"] == DraftStatus.APPROVED.value

    d1_approve_entries = verifier.execute(
        "SELECT * FROM audit_log WHERE target_id=? AND action='draft.approve'", (d1.draft_id,)
    ).fetchall()
    assert d1_approve_entries == [], "no audit entry should exist for the failed first attempt"

    d2_approve_entries = verifier.execute(
        "SELECT * FROM audit_log WHERE target_id=? AND action='draft.approve'", (d2.draft_id,)
    ).fetchall()
    assert len(d2_approve_entries) == 1
