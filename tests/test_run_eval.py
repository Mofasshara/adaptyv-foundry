from evals.golden_set import GOLDEN_SET, GoldenCase
from evals.run_eval import main, run_case


def test_run_case_on_healthy_golden_case_has_no_violations():
    healthy = next(c for c in GOLDEN_SET if c.name == "healthy_affinity_panel")
    result = run_case(healthy)
    assert result.violations == []


def test_run_case_on_all_failed_case_has_no_violations():
    case = next(c for c in GOLDEN_SET if c.name == "all_sequences_failed")
    result = run_case(case)
    assert result.violations == []


def test_run_case_on_control_out_of_range_case_has_no_violations():
    case = next(c for c in GOLDEN_SET if c.name == "control_out_of_range")
    result = run_case(case)
    assert result.violations == []


def test_main_returns_zero_when_all_cases_pass(capsys):
    exit_code = main()
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "PASS" in captured.out
    for case in GOLDEN_SET:
        assert case.name in captured.out


def test_run_case_detects_a_wrong_expected_critical_rule():
    # Real regression case: same experiment as the healthy golden case, but a
    # deliberately WRONG expectation (a critical rule that never fires for it).
    # Proves guard_critical_anomalies_match genuinely flags a mismatch against
    # real detector output -- not just the happy-path fixtures.
    healthy = next(c for c in GOLDEN_SET if c.name == "healthy_affinity_panel")
    wrong_case = GoldenCase(
        name="deliberately_wrong",
        experiment_id=healthy.experiment_id,
        expected_critical_rules=frozenset({"all_sequences_failed"}),
        expected_fact_keys=healthy.expected_fact_keys,
    )

    result = run_case(wrong_case)

    assert result.violations
    assert any("all_sequences_failed" in v for v in result.violations)


def test_main_returns_one_and_prints_fail_when_a_case_has_a_violation(monkeypatch, capsys):
    # Proves main()'s exit-code aggregation and FAIL-printing branch actually
    # fire on a real violation, not just the all-pass happy path.
    healthy = next(c for c in GOLDEN_SET if c.name == "healthy_affinity_panel")
    wrong_case = GoldenCase(
        name="deliberately_wrong",
        experiment_id=healthy.experiment_id,
        expected_critical_rules=frozenset({"all_sequences_failed"}),
        expected_fact_keys=healthy.expected_fact_keys,
    )
    monkeypatch.setattr("evals.run_eval.GOLDEN_SET", [wrong_case])

    exit_code = main()
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "[FAIL] deliberately_wrong" in captured.out
    assert "all_sequences_failed" in captured.out
