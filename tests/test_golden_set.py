from adaptyv import AdaptyvClient
from adaptyv.agents.anomaly import AnomalyDetector
from adaptyv.agents.email import build_fact_sheet
from adaptyv.agents.policy import DEFAULT_POLICY
from evals.golden_set import GOLDEN_SET


def test_golden_set_has_three_cases_with_distinct_names():
    names = {c.name for c in GOLDEN_SET}
    assert len(GOLDEN_SET) == 3
    assert len(names) == 3


def test_each_golden_case_resolves_to_a_real_mock_result():
    client = AdaptyvClient(mock=True)
    for case in GOLDEN_SET:
        results = client.experiments.results(case.experiment_id)
        assert results, f"{case.name}: no results for {case.experiment_id}"


def test_healthy_case_has_no_critical_rules_and_two_facts():
    client = AdaptyvClient(mock=True)
    healthy = next(c for c in GOLDEN_SET if c.name == "healthy_affinity_panel")
    result = client.experiments.results(healthy.experiment_id)[0]
    findings = AnomalyDetector(DEFAULT_POLICY).detect(result)
    critical = {f.rule for f in findings if f.severity.value == "critical"}
    assert critical == healthy.expected_critical_rules == frozenset()
    assert set(build_fact_sheet(result)) == healthy.expected_fact_keys


def test_all_failed_case_matches_detector_output():
    client = AdaptyvClient(mock=True)
    case = next(c for c in GOLDEN_SET if c.name == "all_sequences_failed")
    result = client.experiments.results(case.experiment_id)[0]
    findings = AnomalyDetector(DEFAULT_POLICY).detect(result)
    critical = {f.rule for f in findings if f.severity.value == "critical"}
    assert critical == case.expected_critical_rules == frozenset({"all_sequences_failed"})
    assert build_fact_sheet(result) == {}


def test_control_out_of_range_case_matches_detector_output():
    client = AdaptyvClient(mock=True)
    case = next(c for c in GOLDEN_SET if c.name == "control_out_of_range")
    result = client.experiments.results(case.experiment_id)[0]
    findings = AnomalyDetector(DEFAULT_POLICY).detect(result)
    critical = {f.rule for f in findings if f.severity.value == "critical"}
    assert critical == case.expected_critical_rules == frozenset({"control_out_of_policy"})
    assert set(build_fact_sheet(result)) == case.expected_fact_keys
