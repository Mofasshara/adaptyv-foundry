from typer.testing import CliRunner
from adaptyv.cli import app

runner = CliRunner()


def test_experiments_list():
    r = runner.invoke(app, ["experiments", "list"])
    assert r.exit_code == 0 and "EXP-1001" in r.stdout and "done" in r.stdout


def test_results_get_renders_affinity():
    r = runner.invoke(app, ["results", "get", "aaaaaaaa-0000-0000-0000-000000000001"])
    assert r.exit_code == 0 and "kd_mean" in r.stdout and "1.2e-09" in r.stdout
