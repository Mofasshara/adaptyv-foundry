from adaptyv.models import (
    AffinityResult, ExperimentStatus, ExpInfo, ExperimentListItem,
    KineticInterval, Page, ResultInfo, SequenceInfo,
)

def test_status_enum_matches_real_spec():
    assert ExperimentStatus.DONE.value == "done"
    assert {s.value for s in ExperimentStatus} == {
        "draft", "waiting_for_confirmation", "canceled", "waiting_for_materials",
        "in_production", "quote_sent", "in_queue", "data_analysis", "in_review", "done"}

def test_kinetic_interval_bounds_nullable():
    ki = KineticInterval.model_validate({"value": 1.2e-9})
    assert ki.value == 1.2e-9 and ki.ci_low is None and ki.ci_high is None

def test_affinity_result_sequence_is_object_and_performance_is_mapping():
    ar = AffinityResult.model_validate({
        "sequence": {"aa_string": "MKAA"}, "kd_units": "M", "binding_strength": "strong",
        "positive_control": False, "performance": {"verdict": "pass"}, "replicates": []})
    assert ar.sequence.aa_string == "MKAA"
    assert ar.performance == {"verdict": "pass"} and ar.kd_mean is None

def test_result_summary_discriminates_on_result_type():
    ri = ResultInfo.model_validate({
        "id": "22222222-2222-2222-2222-222222222222", "title": "Affinity",
        "experiment_id": "11111111-1111-1111-1111-111111111111", "result_type": "affinity",
        "created_at": "2026-07-20T10:00:00Z", "metadata": {},
        "summary": [{"result_type": "affinity", "sequence": {"aa_string": "MKAA"},
                     "kd_units": "M", "binding_strength": "strong", "positive_control": True,
                     "performance": {"verdict": "pass"}, "replicates": [], "kd_mean": 2.0e-9}]})
    s = ri.summary[0]
    assert s.result_type == "affinity" and s.positive_control is True and s.kd_mean == 2.0e-9

def test_expinfo_requires_experiment_spec_but_listitem_does_not():
    common = dict(id="11111111-1111-1111-1111-111111111111", code="EXP-1001",
                  status="done", results_status="all", created_at="2026-07-01T10:00:00Z",
                  experiment_url="https://devs.adaptyvbio.com/e/EXP-1001")
    li = ExperimentListItem.model_validate(common)          # no experiment_spec -> ok
    assert li.status is ExperimentStatus.DONE
    exp = ExpInfo.model_validate({**common, "experiment_spec": {"experiment_type": "affinity"}})
    assert exp.experiment_spec.experiment_type.value == "affinity"

def test_page_generic():
    p = Page[ExperimentListItem].model_validate(
        {"items": [], "total": 0, "count": 0, "offset": 0})
    assert p.total == 0 and p.items == []

def test_sequence_detail_nullable_aa_and_nested_experiment():
    s = SequenceInfo.model_validate({
        "id": "33333333-3333-3333-3333-333333333333", "length": 120,
        "is_control": False, "created_at": "2026-07-01T10:00:00Z",
        "experiment": {"experiment_id": "11111111-1111-1111-1111-111111111111",
                       "experiment_code": "EXP-1001"}})
    assert s.aa_string is None and s.experiment.experiment_code == "EXP-1001"
