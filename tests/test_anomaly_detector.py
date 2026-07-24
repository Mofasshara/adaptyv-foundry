from adaptyv.agents.anomaly import AnomalyDetector
from adaptyv.agents.policy import AnomalyPolicy
from adaptyv.governance.models import AnomalySeverity
from adaptyv.models import ResultInfo

POLICY = AnomalyPolicy(version="test", positive_control_kd_min=1e-11,
                       positive_control_kd_max=1e-7, kd_plausible_min=1e-12,
                       kd_plausible_max=1e-6, min_replicates=2)


def _result(summary):
    return ResultInfo.model_validate({
        "id": "r1", "title": "t", "experiment_id": "e1", "result_type": "affinity",
        "created_at": "2026-07-20T10:00:00Z", "metadata": {}, "summary": summary})


def _affinity(name, kd_mean=None, positive_control=False, replicates=None):
    return {"result_type": "affinity", "sequence": {"aa_string": "MKAA", "name": name},
            "kd_units": "M", "binding_strength": "strong", "positive_control": positive_control,
            "performance": {}, "kd_mean": kd_mean, "replicates": replicates or []}


def test_all_failed_is_critical():
    result = _result([_affinity("b1", kd_mean=None), _affinity("b2", kd_mean=None)])
    findings = AnomalyDetector(POLICY).detect(result)
    crit = [f for f in findings if f.rule == "all_sequences_failed"]
    assert len(crit) == 1 and crit[0].severity is AnomalySeverity.CRITICAL
    assert set(crit[0].affected_ids) == {"b1", "b2"}


def test_healthy_result_has_no_critical():
    result = _result([
        _affinity("b1", kd_mean=1e-9, replicates=[{"replicate": 1}, {"replicate": 2}]),
        _affinity("ctrl", kd_mean=2e-9, positive_control=True,
                  replicates=[{"replicate": 1}, {"replicate": 2}]),
    ])
    findings = AnomalyDetector(POLICY).detect(result)
    assert not any(f.severity is AnomalySeverity.CRITICAL for f in findings)


def test_control_out_of_policy_is_critical():
    result = _result([
        _affinity("b1", kd_mean=1e-9, replicates=[{"replicate": 1}, {"replicate": 2}]),
        _affinity("ctrl", kd_mean=1e-3, positive_control=True,
                  replicates=[{"replicate": 1}, {"replicate": 2}]),
    ])
    findings = AnomalyDetector(POLICY).detect(result)
    crit = [f for f in findings if f.rule == "control_out_of_policy"]
    assert len(crit) == 1 and crit[0].severity is AnomalySeverity.CRITICAL
    assert crit[0].affected_ids == ["ctrl"]
    assert crit[0].policy_version == "test"


def test_kd_out_of_bounds_is_warning():
    result = _result([_affinity("b1", kd_mean=1.0,
                                replicates=[{"replicate": 1}, {"replicate": 2}])])
    findings = AnomalyDetector(POLICY).detect(result)
    warn = [f for f in findings if f.rule == "kd_out_of_bounds"]
    assert len(warn) == 1 and warn[0].severity is AnomalySeverity.WARNING


def test_missing_replicates_is_warning():
    result = _result([_affinity("b1", kd_mean=1e-9, replicates=[{"replicate": 1}])])
    findings = AnomalyDetector(POLICY).detect(result)
    warn = [f for f in findings if f.rule == "missing_replicates"]
    assert len(warn) == 1 and warn[0].affected_ids == ["b1"]


def test_deterministic_same_input_same_output():
    result = _result([_affinity("b1", kd_mean=None)])
    d = AnomalyDetector(POLICY)
    assert d.detect(result) == d.detect(result)
