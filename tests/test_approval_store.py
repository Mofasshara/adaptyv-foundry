import pytest

from adaptyv.errors import DraftNotFoundError, InvalidTransitionError, SelfApprovalError
from adaptyv.governance.approval import ApprovalStore
from adaptyv.governance.audit import AuditLog
from adaptyv.governance.db import connect
from adaptyv.governance.models import Actor, DraftStatus

AGENT = Actor(kind="agent", id="watcher")
HUMAN = Actor(kind="human", id="alice")


def _store():
    conn = connect()
    return ApprovalStore(conn, AuditLog(conn))


def test_create_draft_is_pending_and_audited():
    s = _store()
    d = s.create_draft("EXP-1", "Your results are ready.", created_by=AGENT)
    assert d.status is DraftStatus.PENDING_REVIEW
    assert d.created_by.id == "watcher"
    assert s._audit.entries()[-1].action == "draft.create"


def test_agent_cannot_approve():
    s = _store()
    d = s.create_draft("EXP-1", "body", created_by=AGENT)
    with pytest.raises(SelfApprovalError):
        s.approve(d.draft_id, AGENT)


def test_human_approve_moves_to_approved_and_audits():
    s = _store()
    d = s.create_draft("EXP-1", "body", created_by=AGENT)
    out = s.approve(d.draft_id, HUMAN)
    assert out.status is DraftStatus.APPROVED and out.reviewed_by.id == "alice"
    assert s._audit.entries()[-1].action == "draft.approve"


def test_reject_records_note():
    s = _store()
    d = s.create_draft("EXP-1", "body", created_by=AGENT)
    out = s.reject(d.draft_id, HUMAN, note="tone off")
    assert out.status is DraftStatus.REJECTED and out.review_note == "tone off"


def test_cannot_approve_already_approved():
    s = _store()
    d = s.create_draft("EXP-1", "body", created_by=AGENT)
    s.approve(d.draft_id, HUMAN)
    with pytest.raises(InvalidTransitionError):
        s.approve(d.draft_id, HUMAN)


def test_mark_sent_requires_approved():
    s = _store()
    d = s.create_draft("EXP-1", "body", created_by=AGENT)
    with pytest.raises(InvalidTransitionError):
        s.mark_sent(d.draft_id, HUMAN)
    s.approve(d.draft_id, HUMAN)
    assert s.mark_sent(d.draft_id, HUMAN).status is DraftStatus.SENT


def test_get_unknown_raises():
    s = _store()
    with pytest.raises(DraftNotFoundError):
        s.get("nope")
