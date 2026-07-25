from __future__ import annotations

import re

from adaptyv.errors import AnomalyNotAcknowledgedError
from adaptyv.governance.approval import ApprovalStore
from adaptyv.governance.models import Actor, AnomalyFinding, DraftStatus

_PLACEHOLDER = re.compile(r"\{\{([\w-]+)\}\}")
_SCI_NUMBER = re.compile(r"\d+\.\d+e[+-]\d+")


def guard_no_leftover_placeholder_syntax(body: str) -> list[str]:
    tokens = _PLACEHOLDER.findall(body)
    return [f"leftover unresolved placeholder in body: {{{{{t}}}}}" for t in tokens]


def guard_all_numbers_grounded(body: str, fact_sheet: dict[str, str]) -> list[str]:
    grounded_numbers: set[str] = set()
    for value in fact_sheet.values():
        grounded_numbers.update(_SCI_NUMBER.findall(value))
    violations = []
    for number in _SCI_NUMBER.findall(body):
        if number not in grounded_numbers:
            violations.append(f"number '{number}' in body does not trace to any fact_sheet value")
    return violations


def guard_critical_anomalies_match(findings: list[AnomalyFinding], expected: frozenset[str]) -> list[str]:
    actual = frozenset(f.rule for f in findings if f.severity.value == "critical")
    violations = []
    for missing in expected - actual:
        violations.append(f"expected critical rule '{missing}' did not fire")
    for extra in actual - expected:
        violations.append(f"unexpected critical rule '{extra}' fired")
    return violations


def guard_expected_facts_present(fact_sheet: dict[str, str], expected: frozenset[str]) -> list[str]:
    missing = expected - set(fact_sheet)
    return [f"expected fact key '{k}' missing from fact sheet" for k in missing]


def guard_critical_draft_blocks_approval(store: ApprovalStore, draft_id: str, reviewer: Actor,
                                         *, is_critical: bool) -> list[str]:
    draft = store.get(draft_id)
    if draft.status is not DraftStatus.PENDING_REVIEW:
        # Already resolved by an earlier call (approved or rejected) -- nothing new
        # to check, and calling approve()/reject() again would raise
        # InvalidTransitionError. Safe to call this guard more than once.
        return []
    try:
        store.approve(draft_id, reviewer)
    except AnomalyNotAcknowledgedError:
        if not is_critical:
            return ["approval was blocked by the anomaly hard-block, but no critical anomaly was expected"]
        return []
    if is_critical:
        return ["a critical anomaly was expected to hard-block approval, but approve() succeeded"]
    return []
