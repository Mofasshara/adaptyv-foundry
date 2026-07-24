from adaptyv.agents.policy import AnomalyPolicy, DEFAULT_POLICY


def test_default_policy_has_sane_bounds():
    assert DEFAULT_POLICY.version == "v0"
    assert DEFAULT_POLICY.kd_plausible_min < DEFAULT_POLICY.kd_plausible_max
    assert DEFAULT_POLICY.positive_control_kd_min < DEFAULT_POLICY.positive_control_kd_max
    assert DEFAULT_POLICY.min_replicates >= 1


def test_policy_is_strict():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        AnomalyPolicy(version="v0", positive_control_kd_min=1e-11,
                      positive_control_kd_max=1e-7, kd_plausible_min=1e-12,
                      kd_plausible_max=1e-6, min_replicates=2, unexpected_field=1)


def test_policy_is_versionable():
    custom = AnomalyPolicy(version="v1-strict", positive_control_kd_min=1e-10,
                           positive_control_kd_max=1e-8, kd_plausible_min=1e-11,
                           kd_plausible_max=1e-7, min_replicates=3)
    assert custom.version == "v1-strict" and custom.min_replicates == 3
