from adaptyv.governance.audit import AuditLog, GENESIS
from adaptyv.governance.db import connect
from adaptyv.governance.models import Actor


def _log():
    return AuditLog(connect())


def test_record_links_hash_chain():
    log = _log()
    a = Actor(kind="agent", id="watcher")
    e1 = log.record(a, "draft.create", "draft", "d1", "pending_review")
    e2 = log.record(Actor(kind="human", id="alice"), "draft.approve", "draft", "d1", "approved")
    assert e1.prev_hash == GENESIS
    assert e2.prev_hash == e1.entry_hash          # chain links
    assert e1.entry_hash != e2.entry_hash


def test_entries_ordered_and_typed():
    log = _log()
    log.record(Actor(kind="agent", id="w"), "a", "draft", "d1", "ok", {"n": 1})
    entries = log.entries()
    assert [e.id for e in entries] == [1]
    assert entries[0].details == {"n": 1}
    assert entries[0].actor.id == "w"


def test_verify_true_for_intact_chain():
    log = _log()
    for i in range(3):
        log.record(Actor(kind="agent", id="w"), f"a{i}", "draft", "d1", "ok")
    assert log.verify() is True


def test_verify_false_after_tamper():
    conn = connect()
    log = AuditLog(conn)
    log.record(Actor(kind="agent", id="w"), "a0", "draft", "d1", "ok")
    log.record(Actor(kind="agent", id="w"), "a1", "draft", "d1", "ok")
    conn.execute("UPDATE audit_log SET outcome='TAMPERED' WHERE id=1")
    conn.commit()
    assert log.verify() is False


def test_head_empty_and_intact():
    log = _log()
    assert log.head() == (0, GENESIS)
    log.record(Actor(kind="agent", id="w"), "a0", "draft", "d1", "ok")
    log.record(Actor(kind="agent", id="w"), "a1", "draft", "d1", "ok")
    e3 = log.record(Actor(kind="agent", id="w"), "a2", "draft", "d1", "ok")
    assert log.head() == (3, e3.entry_hash)


def test_verify_expected_head_detects_tail_truncation():
    conn = connect()
    log = AuditLog(conn)
    log.record(Actor(kind="agent", id="w"), "a0", "draft", "d1", "ok")
    log.record(Actor(kind="agent", id="w"), "a1", "draft", "d1", "ok")
    log.record(Actor(kind="agent", id="w"), "a2", "draft", "d1", "ok")
    h = log.head()

    conn.execute("DELETE FROM audit_log WHERE id = (SELECT MAX(id) FROM audit_log)")
    conn.commit()

    # Documented limitation: a bare chain-walk can't see a missing tail —
    # the surviving prefix is still internally consistent.
    assert log.verify() is True
    # Pinning the previously-recorded head catches the truncation.
    assert log.verify(expected_head=h) is False
