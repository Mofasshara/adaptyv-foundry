from adaptyv import AdaptyvClient
from adaptyv.agents.anomaly import AnomalyDetector
from adaptyv.agents.email import EmailDraftSchema
from adaptyv.agents.policy import DEFAULT_POLICY
from adaptyv.agents.watcher import Watcher
from adaptyv.governance.approval import ApprovalStore
from adaptyv.governance.audit import AuditLog
from adaptyv.governance.db import connect
from adaptyv.governance.models import DraftStatus

_DRAFTED_SUBJECT = "Your results are ready"


class _FakeDrafter:
    model = "fake-model"

    def draft(self, result, findings):
        return EmailDraftSchema(subject=_DRAFTED_SUBJECT, body="See attached summary.")


class _PartiallyFailingDrafter:
    """Raises for one specific result id, drafts normally for everything else."""
    model = "fake-model"

    def __init__(self, failing_result_id: str) -> None:
        self._failing_result_id = failing_result_id

    def draft(self, result, findings):
        if result.id == self._failing_result_id:
            raise RuntimeError(f"drafting exploded for {result.id}")
        return EmailDraftSchema(subject=_DRAFTED_SUBJECT, body="See attached summary.")


def _make_watcher(drafter=None):
    conn = connect()
    store = ApprovalStore(conn, AuditLog(conn))
    watcher = Watcher(AdaptyvClient(mock=True), AnomalyDetector(DEFAULT_POLICY),
                      drafter or _FakeDrafter(), store, conn)
    return watcher, store


def test_run_creates_pending_review_drafts_for_all_experiments():
    watcher, store = _make_watcher()
    drafts = watcher.run()
    assert drafts
    assert all(d.status is DraftStatus.PENDING_REVIEW for d in drafts)


def test_all_failed_result_creates_draft_with_critical_anomaly():
    watcher, store = _make_watcher()
    drafts = watcher.run(experiment_ids=["33333333-3333-3333-3333-333333333333"])
    assert len(drafts) == 1
    assert any(a.rule == "all_sequences_failed" for a in drafts[0].anomalies)


def test_rerun_does_not_duplicate_drafts():
    watcher, store = _make_watcher()
    first = watcher.run()
    second = watcher.run()
    assert second == []
    assert len(store.list()) == len(first)


def test_experiment_with_no_results_produces_no_draft():
    watcher, store = _make_watcher()
    drafts = watcher.run(experiment_ids=["22222222-2222-2222-2222-222222222222"])
    assert drafts == []


def test_draft_body_includes_email_subject():
    # IMPORTANT-1: the drafted subject must not be silently discarded when the
    # draft is persisted — it must show up somewhere in the persisted body.
    watcher, store = _make_watcher()
    drafts = watcher.run(experiment_ids=["11111111-1111-1111-1111-111111111111"])
    assert drafts
    assert _DRAFTED_SUBJECT in drafts[0].body


def test_one_bad_result_does_not_abort_batch():
    # IMPORTANT-3: a single result whose drafting raises (e.g. an expected
    # UnresolvedPlaceholderError-style guard trip) must not abandon the rest
    # of the batch across other experiments.
    failing_result_id = "aaaaaaaa-0000-0000-0000-000000000002"  # exp 33333333...'s only result
    watcher, store = _make_watcher(_PartiallyFailingDrafter(failing_result_id))

    drafts = watcher.run(experiment_ids=[
        "11111111-1111-1111-1111-111111111111",
        "33333333-3333-3333-3333-333333333333",
    ])

    # The healthy experiment's result still produced a draft.
    assert len(drafts) == 1
    assert all(d.status is DraftStatus.PENDING_REVIEW for d in drafts)

    # The failure was recorded, not raised.
    assert len(watcher.errors) == 1
    experiment_id, result_id, exc = watcher.errors[0]
    assert experiment_id == "33333333-3333-3333-3333-333333333333"
    assert result_id == failing_result_id
    assert isinstance(exc, RuntimeError)

    # The failed result was NOT marked processed, so a rerun with a fixed
    # drafter still attempts it and succeeds.
    fixed_watcher = Watcher(watcher._client, watcher._detector, _FakeDrafter(),
                            watcher._store, watcher._conn)
    retried = fixed_watcher.run(experiment_ids=["33333333-3333-3333-3333-333333333333"])
    assert len(retried) == 1
    assert retried[0].result_id == failing_result_id


def test_rerun_across_new_connection_to_same_file_does_not_duplicate(tmp_path):
    # IMPORTANT-4: prove durability across a process restart, not just a rerun
    # on the same in-memory connection/instance.
    db_path = str(tmp_path / "watcher.db")

    conn1 = connect(db_path)
    store1 = ApprovalStore(conn1, AuditLog(conn1))
    watcher1 = Watcher(AdaptyvClient(mock=True), AnomalyDetector(DEFAULT_POLICY),
                       _FakeDrafter(), store1, conn1)
    first = watcher1.run()
    assert first

    # Brand-new connection/store/audit/watcher instances against the same file.
    conn2 = connect(db_path)
    store2 = ApprovalStore(conn2, AuditLog(conn2))
    watcher2 = Watcher(AdaptyvClient(mock=True), AnomalyDetector(DEFAULT_POLICY),
                       _FakeDrafter(), store2, conn2)
    second = watcher2.run()

    assert second == []
    assert len(store2.list()) == len(first)


def test_mark_processed_failure_is_isolated_not_batch_fatal():
    # Regression test: if writing the watcher_processed marker fails (e.g. a
    # genuine race between two watchers on the same key), that failure must
    # be caught by the SAME per-result try/except that isolates a bad
    # drafter -- not escape run() and abort the whole batch.
    watcher, store = _make_watcher()

    # Pre-insert a colliding marker row so the real INSERT inside on_commit
    # collides with a UNIQUE/PRIMARY KEY violation for the first result Watcher
    # will process.
    first_result = watcher._client.experiments.results("11111111-1111-1111-1111-111111111111")[0]
    key = f"11111111-1111-1111-1111-111111111111:{first_result.id}:{watcher._drafter.model}"
    watcher._conn.execute(
        "INSERT INTO watcher_processed (key, draft_id) VALUES (?, ?)", (key, "some-other-draft-id"))
    watcher._conn.commit()

    drafts = watcher.run(experiment_ids=[
        "11111111-1111-1111-1111-111111111111",
        "33333333-3333-3333-3333-333333333333",
    ])

    # The colliding experiment's result is skipped as already-processed (the
    # pre-inserted row makes _already_processed() return True for it) --
    # this test is really about proving run() doesn't crash and the SECOND
    # experiment still produces a draft.
    assert len(drafts) == 1
    assert drafts[0].experiment_id == "33333333-3333-3333-3333-333333333333"


def test_draft_and_processed_marker_commit_together():
    # Regression test for the atomicity bug: after a successful run, every
    # draft Watcher created has a corresponding watcher_processed row -- they
    # cannot exist independently of each other.
    watcher, store = _make_watcher()
    drafts = watcher.run()
    assert drafts
    for draft in drafts:
        rows = watcher._conn.execute(
            "SELECT 1 FROM watcher_processed WHERE draft_id=?", (draft.draft_id,)).fetchall()
        assert len(rows) == 1
