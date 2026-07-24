from __future__ import annotations

import json
from pathlib import Path

from adaptyv.governance.approval import ApprovalStore
from adaptyv.governance.feedback import FeedbackStore
from evals.golden_set import GoldenCase

DEFAULT_PROMOTED_PATH = Path(__file__).parent / "promoted_golden_cases.json"


def promote_corrections(feedback: FeedbackStore, approval: ApprovalStore,
                        path: Path = DEFAULT_PROMOTED_PATH) -> list[GoldenCase]:
    """Turn every human-corrected draft into a durable golden case, so real
    reviewer corrections become future regression tests (the human-feedback
    flywheel). Idempotent by experiment_id.

    Known limitation: expected_fact_keys defaults to empty for promoted cases
    -- re-deriving it would require re-fetching the original result data,
    which is out of scope here.
    """
    existing = load_promoted_cases(path)
    known_experiment_ids = {c.experiment_id for c in existing}
    promoted: list[GoldenCase] = []
    for correction in feedback.corrections():
        draft = approval.get(correction["draft_id"])
        if draft.experiment_id in known_experiment_ids:
            continue
        critical_rules = frozenset(
            a.rule for a in draft.anomalies if a.severity.value == "critical")
        case = GoldenCase(
            name=f"promoted_{draft.experiment_id[:12]}",
            experiment_id=draft.experiment_id,
            expected_critical_rules=critical_rules,
            expected_fact_keys=frozenset(),
        )
        promoted.append(case)
        known_experiment_ids.add(draft.experiment_id)
    if promoted:
        _save(path, existing + promoted)
    return promoted


def load_promoted_cases(path: Path = DEFAULT_PROMOTED_PATH) -> list[GoldenCase]:
    if not path.exists():
        return []
    raw = json.loads(path.read_text())
    return [GoldenCase(name=r["name"], experiment_id=r["experiment_id"],
                       expected_critical_rules=frozenset(r["expected_critical_rules"]),
                       expected_fact_keys=frozenset(r["expected_fact_keys"])) for r in raw]


def _save(path: Path, cases: list[GoldenCase]) -> None:
    raw = [{"name": c.name, "experiment_id": c.experiment_id,
            "expected_critical_rules": sorted(c.expected_critical_rules),
            "expected_fact_keys": sorted(c.expected_fact_keys)} for c in cases]
    path.write_text(json.dumps(raw, indent=2))
