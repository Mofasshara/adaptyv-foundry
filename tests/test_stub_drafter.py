from adaptyv.agents.stub import StubEmailDrafter
from adaptyv.governance.models import AnomalyFinding
from adaptyv.models import ResultInfo


def _result():
    return ResultInfo.model_validate({
        "id": "r1", "title": "Affinity results", "experiment_id": "e1",
        "result_type": "affinity", "created_at": "2026-07-20T10:00:00Z",
        "metadata": {}, "summary": []})


def test_stub_drafter_has_model_attribute():
    assert StubEmailDrafter().model == "stub-drafter"


def test_stub_drafter_mentions_findings_in_body():
    finding = AnomalyFinding(rule="all_sequences_failed", severity="critical", evidence="0/2 expressed")
    draft = StubEmailDrafter().draft(_result(), [finding])
    assert "all_sequences_failed" in draft.body
    assert "0/2 expressed" in draft.body


def test_stub_drafter_notes_no_anomalies_when_none_given():
    draft = StubEmailDrafter().draft(_result(), [])
    assert "No anomalies detected" in draft.body
