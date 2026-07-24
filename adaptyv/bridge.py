from __future__ import annotations

from typing import Any, Callable

from adaptyv import AdaptyvClient
from adaptyv.agents.anomaly import AnomalyDetector
from adaptyv.agents.email import EmailDraftSchema, EmailDrafter
from adaptyv.agents.policy import DEFAULT_POLICY
from adaptyv.agents.watcher import Watcher
from adaptyv.errors import AdaptyvError
from adaptyv.governance.approval import ApprovalStore
from adaptyv.governance.audit import AuditLog
from adaptyv.governance.db import connect
from adaptyv.models import CostEstimateRequest, CreateExpRequest, ExperimentSpec, SequenceAddRequest, SequenceEntry


class BridgeError(AdaptyvError):
    """Bridge-level error: unknown op or malformed params (not an SDK/API error)."""


def _client(params: dict) -> AdaptyvClient:
    return AdaptyvClient(mock=params.get("mock", True))


def _sequence_entries(raw: list[dict]) -> list[SequenceEntry]:
    return [SequenceEntry(aa_string=s["aa_string"], name=s.get("name")) for s in raw]


def _op_list_experiments(params: dict) -> Any:
    client = _client(params)
    exps = client.experiments.list(search=params.get("search"), filter=params.get("filter"),
                                   sort=params.get("sort"), limit=params.get("limit"),
                                   offset=params.get("offset"))
    return [e.model_dump(mode="json") for e in exps]


def _op_get_experiment_status(params: dict) -> Any:
    client = _client(params)
    exp = client.experiments.get(params["experiment_id"])
    return exp.model_dump(mode="json")


def _op_create_experiment_with_sequences(params: dict) -> Any:
    client = _client(params)
    spec = ExperimentSpec(experiment_type=params["experiment_type"],
                          sequences=_sequence_entries(params.get("sequences", [])),
                          target_id=params.get("target_id"))
    request = CreateExpRequest(name=params["name"], experiment_spec=spec,
                               skip_draft=params.get("skip_draft"))
    return client.experiments.create(request).model_dump(mode="json")


def _op_add_sequences(params: dict) -> Any:
    client = _client(params)
    request = SequenceAddRequest(experiment_code=params["experiment_code"],
                                 sequences=_sequence_entries(params.get("sequences", [])))
    return client.sequences.add(request).model_dump(mode="json")


def _op_search_targets(params: dict) -> Any:
    client = _client(params)
    targets = client.targets.list(search=params.get("search"),
                                  selfservice_only=params.get("selfservice_only"),
                                  detailed=params.get("detailed"))
    return [t.model_dump(mode="json") for t in targets]


def _op_estimate_cost(params: dict) -> Any:
    client = _client(params)
    spec = ExperimentSpec(experiment_type=params["experiment_type"],
                          sequences=_sequence_entries(params.get("sequences", [])),
                          target_id=params.get("target_id"))
    return client.experiments.cost_estimate(CostEstimateRequest(experiment_spec=spec)).model_dump(mode="json")


def _op_get_results(params: dict) -> Any:
    client = _client(params)
    results = client.experiments.results(params["experiment_id"])
    return [r.model_dump(mode="json") for r in results]


class _StubDrafter:
    """Zero-credential drafter for the demo/default path: no Claude call."""
    model = "stub-drafter"

    def draft(self, result, findings) -> EmailDraftSchema:
        lines = [f"Results are in for {result.title}."]
        for f in findings:
            lines.append(f"[{f.severity.value.upper()}] {f.rule}: {f.evidence}")
        if not findings:
            lines.append("No anomalies detected.")
        return EmailDraftSchema(subject=f"Update: {result.title}", body="\n".join(lines))


def _op_draft_customer_update(params: dict) -> Any:
    client = _client(params)
    conn = connect(params.get("db", "adaptyv_governance.db"))
    store = ApprovalStore(conn, AuditLog(conn))
    if params.get("mock_llm", True):
        drafter = _StubDrafter()
    else:
        import anthropic
        drafter = EmailDrafter(client=anthropic.Anthropic())
    watcher = Watcher(client, AnomalyDetector(DEFAULT_POLICY), drafter, store, conn)
    experiment_id = params["experiment_id"]
    drafts = watcher.run(experiment_ids=[experiment_id])
    if drafts:
        draft = drafts[0]
    else:
        existing = [d for d in store.list() if d.experiment_id == experiment_id]
        if not existing:
            raise BridgeError(f"no results available yet for experiment {experiment_id}")
        draft = sorted(existing, key=lambda d: d.created_at)[-1]
    return draft.model_dump(mode="json")


_OPS: dict[str, Callable[[dict], Any]] = {
    "list_experiments": _op_list_experiments,
    "get_experiment_status": _op_get_experiment_status,
    "create_experiment_with_sequences": _op_create_experiment_with_sequences,
    "add_sequences": _op_add_sequences,
    "search_targets": _op_search_targets,
    "estimate_cost": _op_estimate_cost,
    "get_results": _op_get_results,
    "draft_customer_update": _op_draft_customer_update,
}


def handle_request(request: dict) -> dict:
    op = request.get("op")
    params = request.get("params", {})
    if op not in _OPS:
        return {"ok": False, "error": {"type": "BridgeError", "message": f"unknown op '{op}'"}}
    try:
        return {"ok": True, "result": _OPS[op](params)}
    except AdaptyvError as exc:
        return {"ok": False, "error": {"type": type(exc).__name__, "message": exc.message}}
    except KeyError as exc:
        return {"ok": False, "error": {"type": "BridgeError", "message": f"missing required param: {exc}"}}
    except (TypeError, ValueError) as exc:
        return {"ok": False, "error": {"type": "BridgeError", "message": f"invalid params: {exc}"}}
    except Exception as exc:
        # Catch-all: the bridge's contract is that failure is ALWAYS signaled
        # via the {"ok": False} envelope, never via an uncaught traceback or a
        # nonzero process exit code. Anything not matched by the specific
        # excepts above (e.g. sqlite3.OperationalError from an unwritable db
        # path, or any future op implementation bug) must still be reported
        # through this envelope rather than escaping handle_request.
        return {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
