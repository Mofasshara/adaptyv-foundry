from adaptyv.governance.approval import ApprovalStore
from adaptyv.governance.audit import AuditLog
from adaptyv.governance.db import connect
from adaptyv.governance.feedback import FeedbackStore
from adaptyv.governance.models import Actor, AnomalyFinding
from evals.flywheel import load_promoted_cases, promote_corrections

HUMAN = Actor(kind="human", id="alice")
AGENT = Actor(kind="agent", id="watcher")


def _setup():
    conn = connect()
    approval = ApprovalStore(conn, AuditLog(conn))
    feedback = FeedbackStore(conn)
    return approval, feedback


def test_promote_corrections_derives_a_case_from_a_rejected_draft(tmp_path):
    approval, feedback = _setup()
    finding = AnomalyFinding(rule="control_out_of_policy", severity="critical", evidence="e")
    draft = approval.create_draft("exp-promoted-1", "bad body", anomalies=[finding], created_by=AGENT)
    approval.reject(draft.draft_id, HUMAN, note="wrong tone")
    feedback.record_correction(draft.draft_id, "corrected body text", HUMAN)

    path = tmp_path / "promoted.json"
    promoted = promote_corrections(feedback, approval, path=path)

    assert len(promoted) == 1
    assert promoted[0].experiment_id == "exp-promoted-1"
    assert promoted[0].expected_critical_rules == frozenset({"control_out_of_policy"})
    assert path.exists()


def test_promote_corrections_is_idempotent(tmp_path):
    approval, feedback = _setup()
    draft = approval.create_draft("exp-promoted-2", "body", anomalies=[], created_by=AGENT)
    feedback.record_correction(draft.draft_id, "corrected", HUMAN)
    path = tmp_path / "promoted.json"

    first = promote_corrections(feedback, approval, path=path)
    second = promote_corrections(feedback, approval, path=path)

    assert len(first) == 1
    assert len(second) == 0  # nothing new to promote
    assert len(load_promoted_cases(path)) == 1


def test_load_promoted_cases_returns_empty_list_when_file_absent(tmp_path):
    assert load_promoted_cases(tmp_path / "does_not_exist.json") == []
