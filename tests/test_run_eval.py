from evals.golden_set import GOLDEN_SET
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
