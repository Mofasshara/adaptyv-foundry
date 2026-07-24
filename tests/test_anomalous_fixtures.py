from adaptyv import AdaptyvClient
from adaptyv.agents.anomaly import AnomalyDetector
from adaptyv.agents.policy import DEFAULT_POLICY
from adaptyv.governance.models import AnomalySeverity


def test_all_failed_fixture_trips_critical():
    client = AdaptyvClient(mock=True)
    results = client.experiments.results("33333333-3333-3333-3333-333333333333")
    findings = AnomalyDetector(DEFAULT_POLICY).detect(results[0])
    assert any(f.rule == "all_sequences_failed" and f.severity is AnomalySeverity.CRITICAL
              for f in findings)


def test_control_out_of_range_fixture_trips_critical():
    client = AdaptyvClient(mock=True)
    results = client.experiments.results("44444444-4444-4444-4444-444444444444")
    findings = AnomalyDetector(DEFAULT_POLICY).detect(results[0])
    assert any(f.rule == "control_out_of_policy" and f.severity is AnomalySeverity.CRITICAL
              for f in findings)


def test_existing_experiments_still_present():
    exps = AdaptyvClient(mock=True).experiments.list()
    codes = {e.code for e in exps}
    assert {"EXP-1001", "EXP-1002", "EXP-1003", "EXP-1004"} <= codes
