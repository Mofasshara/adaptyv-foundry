from adaptyv import AdaptyvClient
from adaptyv.agents.anomaly import AnomalyDetector
from adaptyv.agents.email import EmailDraftSchema
from adaptyv.agents.policy import DEFAULT_POLICY
from adaptyv.agents.watcher import Watcher
from adaptyv.governance.approval import ApprovalStore
from adaptyv.governance.audit import AuditLog
from adaptyv.governance.db import connect
from adaptyv.governance.models import DraftStatus


class _FakeDrafter:
    model = "fake-model"

    def draft(self, result, findings):
        return EmailDraftSchema(subject="Your results", body="See attached summary.")


def _make_watcher():
    conn = connect()
    store = ApprovalStore(conn, AuditLog(conn))
    watcher = Watcher(AdaptyvClient(mock=True), AnomalyDetector(DEFAULT_POLICY),
                      _FakeDrafter(), store, conn)
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
