from __future__ import annotations
import typer
from adaptyv import AdaptyvClient
from adaptyv.models import AffinityResultSummary

app = typer.Typer(help="Adaptyv Foundry SDK CLI")
exp = typer.Typer(); res = typer.Typer()
app.add_typer(exp, name="experiments"); app.add_typer(res, name="results")

def _c(mock): return AdaptyvClient(mock=mock)

@exp.command("list")
def experiments_list(mock: bool = typer.Option(True)):
    for e in _c(mock).experiments.list():
        typer.echo(f"{e.code}\t{e.status.value}\t{e.name or ''}")

@res.command("get")
def results_get(result_id: str, mock: bool = typer.Option(True)):
    r = _c(mock).results.get(result_id)
    typer.echo(r.title)
    for s in r.summary:
        if isinstance(s, AffinityResultSummary):
            typer.echo(f"  {s.sequence.name or s.sequence.aa_string}: kd_mean={s.kd_mean} {s.kd_units}"
                       f"  perf={s.performance}  control={s.positive_control}")
        else:
            typer.echo(f"  {s.sequence_name or s.sequence_id}: tm={s.tm}")

if __name__ == "__main__":
    app()
