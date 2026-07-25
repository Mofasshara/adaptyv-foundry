from __future__ import annotations

import sys
from dataclasses import dataclass

from adaptyv import AdaptyvClient
from adaptyv.agents.anomaly import AnomalyDetector
from adaptyv.agents.email import EmailDrafter, build_fact_sheet
from adaptyv.agents.policy import DEFAULT_POLICY
from adaptyv.governance.approval import ApprovalStore
from adaptyv.governance.audit import AuditLog
from adaptyv.governance.db import connect
from adaptyv.governance.models import Actor
from evals.fake_llm import DeterministicFakeClient
from evals.flywheel import load_promoted_cases
from evals.golden_set import GOLDEN_SET, GoldenCase
from evals.guards import (guard_critical_anomalies_match, guard_critical_draft_blocks_approval,
                          guard_expected_facts_present)

HUMAN_REVIEWER = Actor(kind="human", id="eval-suite")
AGENT_DRAFTER = Actor(kind="agent", id="eval-suite-watcher")


@dataclass
class EvalCaseResult:
    case: GoldenCase
    violations: list[str]


def run_case(case: GoldenCase) -> EvalCaseResult:
    client = AdaptyvClient(mock=True)
    result = client.experiments.results(case.experiment_id)[0]
    findings = AnomalyDetector(DEFAULT_POLICY).detect(result)
    fact_sheet = build_fact_sheet(result)
    drafter = EmailDrafter(client=DeterministicFakeClient())
    draft_email = drafter.draft(result, findings)

    violations: list[str] = []
    violations += guard_critical_anomalies_match(findings, case.expected_critical_rules)
    violations += guard_expected_facts_present(fact_sheet, case.expected_fact_keys)

    conn = connect()
    store = ApprovalStore(conn, AuditLog(conn))
    draft = store.create_draft(case.experiment_id, draft_email.body, result_id=result.id,
                               anomalies=findings, created_by=AGENT_DRAFTER)
    is_critical = bool(case.expected_critical_rules)
    violations += guard_critical_draft_blocks_approval(store, draft.draft_id, HUMAN_REVIEWER,
                                                       is_critical=is_critical)
    return EvalCaseResult(case=case, violations=violations)


def main() -> int:
    results: list[EvalCaseResult] = []
    for case in GOLDEN_SET + load_promoted_cases():
        try:
            results.append(run_case(case))
        except Exception as exc:
            results.append(EvalCaseResult(
                case=case,
                violations=[f"eval crashed while running this case: {type(exc).__name__}: {exc}"]))
    total_violations = 0
    for r in results:
        status = "PASS" if not r.violations else "FAIL"
        print(f"[{status}] {r.case.name}")
        for v in r.violations:
            print(f"    - {v}")
        total_violations += len(r.violations)
    print(f"\n{len(results)} cases, {total_violations} violation(s)")
    return 0 if total_violations == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
