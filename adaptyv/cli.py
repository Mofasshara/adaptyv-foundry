from __future__ import annotations
import typer
from adaptyv import AdaptyvClient
from adaptyv.models import AffinityResultSummary
from adaptyv.errors import GovernanceError
from adaptyv.governance.approval import ApprovalStore
from adaptyv.governance.audit import AuditLog
from adaptyv.governance.db import connect
from adaptyv.governance.models import Actor, has_unacknowledged_critical

app = typer.Typer(help="Adaptyv Foundry SDK CLI")
exp = typer.Typer(); res = typer.Typer()
review = typer.Typer(help="Human review of customer-update drafts")
audit = typer.Typer(help="Audit trail")
app.add_typer(exp, name="experiments"); app.add_typer(res, name="results")
app.add_typer(review, name="review")
app.add_typer(audit, name="audit")

def _c(mock): return AdaptyvClient(mock=mock)

def _store(db: str):
    conn = connect(db)
    return ApprovalStore(conn, AuditLog(conn))

def _human(name: str) -> Actor:
    return Actor(kind="human", id=name)

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

@review.command("list")
def review_list(db: str = typer.Option("adaptyv_governance.db")):
    for d in _store(db).list():
        flag = "  ⚠CRITICAL" if has_unacknowledged_critical(d) else ""
        typer.echo(f"{d.draft_id[:8]}  {d.status.value:14} {d.experiment_id}{flag}")

@review.command("show")
def review_show(draft_id: str, db: str = typer.Option("adaptyv_governance.db")):
    _run(lambda: _show(_store(db), draft_id))

def _show(store, draft_id):
    d = store.get(draft_id)
    typer.echo(f"[{d.status.value}] {d.experiment_id}\n\n{d.body}\n")
    for a in d.anomalies:
        typer.echo(f"  - {a.severity.value.upper()}: {a.rule} — {a.evidence}")

@review.command("approve")
def review_approve(draft_id: str, by: str = typer.Option(...), db: str = typer.Option("adaptyv_governance.db")):
    _run(lambda: typer.echo(f"approved: {_store(db).approve(draft_id, _human(by)).draft_id}"))

@review.command("reject")
def review_reject(draft_id: str, by: str = typer.Option(...), note: str = typer.Option(""),
                  db: str = typer.Option("adaptyv_governance.db")):
    _run(lambda: typer.echo(f"rejected: {_store(db).reject(draft_id, _human(by), note).draft_id}"))

@review.command("ack")
def review_ack(draft_id: str, by: str = typer.Option(...), db: str = typer.Option("adaptyv_governance.db")):
    _run(lambda: typer.echo(f"acknowledged: {_store(db).acknowledge_anomaly(draft_id, _human(by)).draft_id}"))

@audit.command("list")
def audit_list(db: str = typer.Option("adaptyv_governance.db")):
    conn = connect(db)
    for e in AuditLog(conn).entries():
        typer.echo(f"{e.id:3}  {e.ts}  {e.actor.kind.value}:{e.actor.id}  {e.action}  {e.target_id}")

@audit.command("verify")
def audit_verify(db: str = typer.Option("adaptyv_governance.db")):
    ok = AuditLog(connect(db)).verify()
    typer.echo("OK — chain intact" if ok else "FAILED — chain tampered")
    raise typer.Exit(0 if ok else 1)

def _run(fn):
    try:
        fn()
    except GovernanceError as exc:
        typer.echo(f"error: {exc.message}")
        raise typer.Exit(1)

if __name__ == "__main__":
    app()
