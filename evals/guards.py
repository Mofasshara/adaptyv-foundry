from __future__ import annotations

from adaptyv.errors import AnomalyNotAcknowledgedError
from adaptyv.governance.approval import ApprovalStore
from adaptyv.governance.models import Actor, AnomalyFinding, DraftStatus

# No leftover-placeholder / ungrounded-number guards live here: EmailDrafter.draft()
# itself raises UnresolvedPlaceholderError for both cases (deny-by-default -- any
# raw digit or malformed/leftover brace fails before draft() ever returns). A
# second, separate implementation of the same check here would just be a second
# place for the two to drift out of sync, which is exactly what happened before.
# If draft() ever lets something bad through, run_case()'s try/except reports it
# as a crashed case -- which is the correct, louder failure mode.


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
