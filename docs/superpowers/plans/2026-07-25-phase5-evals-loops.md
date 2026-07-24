# Phase 5 — Eval Suite + Feedback Loops — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the agent's output trustworthy and self-improving. A golden set anchors
expectations to the real demo fixtures; deterministic guards enforce them as a CI gate
(no hallucinated numbers, critical anomalies always flagged); `make eval` turns that
into a repeatable eval→improve cycle; a human-feedback flywheel promotes real reviewer
corrections into the golden set; and an autonomous watch loop makes the agent
operate continuously instead of one-shot. **Scope (user-selected):** core (Tasks 1–3)
+ flywheel (Task 4) + autonomous watch (Task 5) — the LLM-judge is explicitly out of
scope for this phase (it requires live, costed Anthropic API calls, a decision
reserved for the user).

**Architecture:** `evals/` is a new top-level package, read-only with respect to
Phases 1–4 (it imports `adaptyv.*`, never the reverse). The golden set is built from
the SDK's *real* mock fixtures (EXP-1001/1003/1004) — not synthetic data — so the eval
suite is anchored to the same demo data a reviewer would see. The eval loop exercises
the *real* `EmailDrafter.draft()` (including its `substitute_facts` guard) against a
deterministic fake Anthropic client, never the network. The flywheel promotes rejected,
human-corrected drafts into durable golden cases (`evals/promoted_golden_cases.json`).
The autonomous watch loop is a thin CLI wrapper around the already-idempotent
`Watcher.run()` from Phase 3 — no new idempotency logic needed, just a poll interval.

**Tech Stack:** Python 3.11+, pydantic v2 (reusing existing models), stdlib only for
new code (`sqlite3` already a dependency via governance; `time`/`json`/`re` stdlib).

## Global Constraints

- Python 3.11+, sync only. Work inside the repo-local venv (`. .venv/bin/activate`);
  use `python3 -m pytest`.
- **No live Anthropic API calls anywhere in this phase** — the eval loop's "drafting"
  step uses a deterministic fake client (same pattern as Phase 3's tests), never
  `anthropic.Anthropic()`.
- Deterministic guards are the CI gate: `evals/run_eval.py`'s `main()` exits nonzero if
  any golden case has a guard violation.
- `evals/` code never imports from `tests/` or vice versa; both import from `adaptyv.*`.
- TDD: failing test first (fails for the real reason), then minimal code, green, commit.
- Commit messages exactly as written below; **NO `Co-Authored-By`/`Generated with`
  trailer**. Commit only each task's own files with explicit `git add <paths>` (never
  `-A`/`-am`); do **not** touch `ROADMAP.md`/docs in task commits.
- End every task with `python3 -m pytest -q` fully green, output pristine.

---

### Task 1: Golden set (anchored to real demo fixtures)

**Files:**
- Create: `evals/__init__.py`
- Create: `evals/golden_set.py`
- Test: `tests/test_golden_set.py`

**Interfaces:**
- Produces `evals.golden_set.GoldenCase` (frozen dataclass): `name: str`,
  `experiment_id: str`, `expected_critical_rules: frozenset[str]`,
  `expected_fact_keys: frozenset[str]`.
- `evals.golden_set.GOLDEN_SET: list[GoldenCase]` — 3 cases built from the SDK's real
  mock fixtures: a healthy affinity panel (EXP-1001, zero critical rules), an
  all-sequences-failed panel (EXP-1003, `all_sequences_failed` critical), and a
  control-out-of-range panel (EXP-1004, `control_out_of_policy` critical).

- [ ] **Step 1: Write the failing test** — `tests/test_golden_set.py`:
```python
from adaptyv import AdaptyvClient
from adaptyv.agents.anomaly import AnomalyDetector
from adaptyv.agents.email import build_fact_sheet
from adaptyv.agents.policy import DEFAULT_POLICY
from evals.golden_set import GOLDEN_SET


def test_golden_set_has_three_cases_with_distinct_names():
    names = {c.name for c in GOLDEN_SET}
    assert len(GOLDEN_SET) == 3
    assert len(names) == 3


def test_each_golden_case_resolves_to_a_real_mock_result():
    client = AdaptyvClient(mock=True)
    for case in GOLDEN_SET:
        results = client.experiments.results(case.experiment_id)
        assert results, f"{case.name}: no results for {case.experiment_id}"


def test_healthy_case_has_no_critical_rules_and_two_facts():
    client = AdaptyvClient(mock=True)
    healthy = next(c for c in GOLDEN_SET if c.name == "healthy_affinity_panel")
    result = client.experiments.results(healthy.experiment_id)[0]
    findings = AnomalyDetector(DEFAULT_POLICY).detect(result)
    critical = {f.rule for f in findings if f.severity.value == "critical"}
    assert critical == healthy.expected_critical_rules == frozenset()
    assert set(build_fact_sheet(result)) == healthy.expected_fact_keys


def test_all_failed_case_matches_detector_output():
    client = AdaptyvClient(mock=True)
    case = next(c for c in GOLDEN_SET if c.name == "all_sequences_failed")
    result = client.experiments.results(case.experiment_id)[0]
    findings = AnomalyDetector(DEFAULT_POLICY).detect(result)
    critical = {f.rule for f in findings if f.severity.value == "critical"}
    assert critical == case.expected_critical_rules == frozenset({"all_sequences_failed"})
    assert build_fact_sheet(result) == {}


def test_control_out_of_range_case_matches_detector_output():
    client = AdaptyvClient(mock=True)
    case = next(c for c in GOLDEN_SET if c.name == "control_out_of_range")
    result = client.experiments.results(case.experiment_id)[0]
    findings = AnomalyDetector(DEFAULT_POLICY).detect(result)
    critical = {f.rule for f in findings if f.severity.value == "critical"}
    assert critical == case.expected_critical_rules == frozenset({"control_out_of_policy"})
    assert set(build_fact_sheet(result)) == case.expected_fact_keys
```

- [ ] **Step 2: Run** `python3 -m pytest tests/test_golden_set.py -q` → FAIL
  (`ModuleNotFoundError: No module named 'evals'`).

- [ ] **Step 3: Implement** — `evals/__init__.py`: (empty file).
  `evals/golden_set.py`:
```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GoldenCase:
    """A real mock-fixture experiment plus what a correct agent run over it
    must produce. Anchored to adaptyv/mocks/fixtures/*.json — not synthetic
    data — so the eval suite regresses against the same demo data a reviewer
    sees."""
    name: str
    experiment_id: str
    expected_critical_rules: frozenset[str]
    expected_fact_keys: frozenset[str]


GOLDEN_SET: list[GoldenCase] = [
    GoldenCase(
        name="healthy_affinity_panel",
        experiment_id="11111111-1111-1111-1111-111111111111",  # EXP-1001
        expected_critical_rules=frozenset(),
        expected_fact_keys=frozenset({"kd_mean_binder-1", "kd_mean_pos-control"}),
    ),
    GoldenCase(
        name="all_sequences_failed",
        experiment_id="33333333-3333-3333-3333-333333333333",  # EXP-1003
        expected_critical_rules=frozenset({"all_sequences_failed"}),
        expected_fact_keys=frozenset(),
    ),
    GoldenCase(
        name="control_out_of_range",
        experiment_id="44444444-4444-4444-4444-444444444444",  # EXP-1004
        expected_critical_rules=frozenset({"control_out_of_policy"}),
        expected_fact_keys=frozenset({"kd_mean_binder-5", "kd_mean_pos-control"}),
    ),
]
```

- [ ] **Step 4: Run** → PASS. **Step 5: Commit**
```bash
git add evals/__init__.py evals/golden_set.py tests/test_golden_set.py
git commit -m "feat: golden set anchored to real mock-fixture experiments"
```

---

### Task 2: Deterministic guards

**Files:**
- Create: `evals/guards.py`
- Test: `tests/test_guards.py`

**Interfaces:**
- Every guard function returns `list[str]` (violation messages; empty = pass) so a
  caller can aggregate without exception-based control flow.
- `guard_no_leftover_placeholder_syntax(body: str) -> list[str]`
- `guard_all_numbers_grounded(body: str, fact_sheet: dict[str, str]) -> list[str]` —
  scans `body` for scientific-notation numbers (the shape `build_fact_sheet` emits,
  e.g. `1.20e-09`) and flags any that don't appear inside some `fact_sheet` value —
  defense-in-depth against a number ever entering the body outside the placeholder
  path.
- `guard_critical_anomalies_match(findings: list[AnomalyFinding], expected: frozenset[str]) -> list[str]`
- `guard_expected_facts_present(fact_sheet: dict[str, str], expected: frozenset[str]) -> list[str]`
- `guard_critical_draft_blocks_approval(store: ApprovalStore, draft_id: str, reviewer: Actor, is_critical: bool) -> list[str]` —
  integration guard: attempts `store.approve(draft_id, reviewer)`; if `is_critical` and
  it does NOT raise `AnomalyNotAcknowledgedError`, that's a violation (the hard-block
  failed); if not `is_critical` and it DOES raise, that's also a violation.

- [ ] **Step 1: Write the failing test** — `tests/test_guards.py`:
```python
import pytest

from adaptyv.errors import AnomalyNotAcknowledgedError
from adaptyv.governance.approval import ApprovalStore
from adaptyv.governance.audit import AuditLog
from adaptyv.governance.db import connect
from adaptyv.governance.models import Actor, AnomalyFinding
from evals.guards import (guard_all_numbers_grounded, guard_critical_anomalies_match,
                          guard_critical_draft_blocks_approval, guard_expected_facts_present,
                          guard_no_leftover_placeholder_syntax)

HUMAN = Actor(kind="human", id="alice")
AGENT = Actor(kind="agent", id="watcher")


def test_no_leftover_placeholder_passes_on_clean_body():
    assert guard_no_leftover_placeholder_syntax("All good, no tokens here.") == []


def test_no_leftover_placeholder_flags_a_stray_token():
    violations = guard_no_leftover_placeholder_syntax("Kd was {{kd_mean_x}}.")
    assert violations and "kd_mean_x" in violations[0]


def test_all_numbers_grounded_passes_when_number_traces_to_fact_sheet():
    fact_sheet = {"kd_mean_binder-1": "1.20e-09 M"}
    assert guard_all_numbers_grounded("Kd was 1.20e-09 M.", fact_sheet) == []


def test_all_numbers_grounded_flags_an_ungrounded_number():
    violations = guard_all_numbers_grounded("Kd was 9.99e-09 M.", {"kd_mean_binder-1": "1.20e-09 M"})
    assert violations and "9.99e-09" in violations[0]


def test_critical_anomalies_match_passes_on_exact_match():
    findings = [AnomalyFinding(rule="all_sequences_failed", severity="critical", evidence="e")]
    assert guard_critical_anomalies_match(findings, frozenset({"all_sequences_failed"})) == []


def test_critical_anomalies_match_flags_missing_and_extra():
    findings = [AnomalyFinding(rule="control_out_of_policy", severity="critical", evidence="e")]
    violations = guard_critical_anomalies_match(findings, frozenset({"all_sequences_failed"}))
    assert any("all_sequences_failed" in v for v in violations)
    assert any("control_out_of_policy" in v for v in violations)


def test_expected_facts_present_passes_and_fails_correctly():
    assert guard_expected_facts_present({"kd_mean_x": "v"}, frozenset({"kd_mean_x"})) == []
    violations = guard_expected_facts_present({}, frozenset({"kd_mean_x"}))
    assert violations and "kd_mean_x" in violations[0]


def _store():
    conn = connect()
    return ApprovalStore(conn, AuditLog(conn))


def test_critical_draft_blocks_approval_passes_when_hard_block_holds():
    store = _store()
    finding = AnomalyFinding(rule="all_sequences_failed", severity="critical", evidence="e")
    draft = store.create_draft("exp-1", "body", anomalies=[finding], created_by=AGENT)
    assert guard_critical_draft_blocks_approval(store, draft.draft_id, HUMAN, is_critical=True) == []


def test_critical_draft_blocks_approval_flags_a_broken_hard_block():
    store = _store()
    draft = store.create_draft("exp-1", "body", anomalies=[], created_by=AGENT)
    # is_critical=True but no critical anomaly was actually attached -> approve()
    # will succeed, and the guard must flag that mismatch.
    violations = guard_critical_draft_blocks_approval(store, draft.draft_id, HUMAN, is_critical=True)
    assert violations
```

- [ ] **Step 2: Run** → FAIL (`ModuleNotFoundError: No module named 'evals.guards'`).

- [ ] **Step 3: Implement** — `evals/guards.py`:
```python
from __future__ import annotations

import re

from adaptyv.errors import AnomalyNotAcknowledgedError
from adaptyv.governance.approval import ApprovalStore
from adaptyv.governance.models import Actor, AnomalyFinding

_PLACEHOLDER = re.compile(r"\{\{([\w-]+)\}\}")
_SCI_NUMBER = re.compile(r"\d+\.\d+e[+-]\d+")


def guard_no_leftover_placeholder_syntax(body: str) -> list[str]:
    tokens = _PLACEHOLDER.findall(body)
    return [f"leftover unresolved placeholder in body: {{{{{t}}}}}" for t in tokens]


def guard_all_numbers_grounded(body: str, fact_sheet: dict[str, str]) -> list[str]:
    grounded_values = " ".join(fact_sheet.values())
    violations = []
    for number in _SCI_NUMBER.findall(body):
        if number not in grounded_values:
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
    try:
        store.approve(draft_id, reviewer)
    except AnomalyNotAcknowledgedError:
        if not is_critical:
            return ["approval was blocked by the anomaly hard-block, but no critical anomaly was expected"]
        return []
    if is_critical:
        return ["a critical anomaly was expected to hard-block approval, but approve() succeeded"]
    return []
```

- [ ] **Step 4: Run** → PASS. **Step 5: Commit**
```bash
git add evals/guards.py tests/test_guards.py
git commit -m "feat: deterministic eval guards (grounding, anomaly-match, hard-block)"
```

---

### Task 3: Eval→improve loop (`make eval`)

**Files:**
- Create: `evals/fake_llm.py`
- Create: `evals/run_eval.py`
- Create: `Makefile`
- Test: `tests/test_run_eval.py`

**Interfaces:**
- `evals.fake_llm.DeterministicFakeClient` — a fake Anthropic client (duck-typed:
  `.messages.parse(**kwargs) -> object with .parsed_output`) that reads the fact
  placeholder tokens Ω`EmailDrafter` lists in its prompt and echoes each one back
  inside `{{token}}` syntax in a templated body — so the REAL `EmailDrafter.draft()`
  (including its real `substitute_facts` call) runs end-to-end with zero network I/O.
- `evals.run_eval.run_case(case: GoldenCase) -> EvalCaseResult` (dataclass:
  `case: GoldenCase`, `violations: list[str]`).
- `evals.run_eval.main() -> int` — runs the full `GOLDEN_SET`, prints a per-case
  PASS/FAIL report + summary, returns `0` if zero total violations else `1`.
- `python3 -m evals.run_eval` and `make eval` both run it.

- [ ] **Step 1: Write the failing test** — `tests/test_run_eval.py`:
```python
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
```

- [ ] **Step 2: Run** → FAIL (`ModuleNotFoundError: No module named 'evals.fake_llm'`).

- [ ] **Step 3: Implement** — `evals/fake_llm.py`:
```python
from __future__ import annotations

import re

from adaptyv.agents.email import EmailDraftSchema

_PROMPT_TOKEN = re.compile(r"\{\{([\w-]+)\}\}")


class _FakeParseResponse:
    def __init__(self, parsed_output: EmailDraftSchema) -> None:
        self.parsed_output = parsed_output


class _FakeMessages:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def parse(self, **kwargs) -> _FakeParseResponse:
        self.calls.append(kwargs)
        prompt = str(kwargs.get("messages", [{}])[0].get("content", ""))
        fact_ids = _PROMPT_TOKEN.findall(prompt)
        if fact_ids:
            lines = [f"Measured value for {fid}: {{{{{fid}}}}}." for fid in fact_ids]
        else:
            lines = ["No quantitative results are available for this update."]
        return _FakeParseResponse(EmailDraftSchema(subject="Eval run update", body="\n".join(lines)))


class DeterministicFakeClient:
    """A fake Anthropic client for the eval loop: echoes back every fact
    placeholder token the real EmailDrafter offers, so `draft()`'s actual
    substitution + guard logic is genuinely exercised — no network call,
    fully reproducible."""

    def __init__(self) -> None:
        self.messages = _FakeMessages()
```

- [ ] **Step 4: Implement** — `evals/run_eval.py`:
```python
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
from evals.golden_set import GOLDEN_SET, GoldenCase
from evals.guards import (guard_all_numbers_grounded, guard_critical_anomalies_match,
                          guard_critical_draft_blocks_approval, guard_expected_facts_present,
                          guard_no_leftover_placeholder_syntax)

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
    violations += guard_no_leftover_placeholder_syntax(draft_email.body)
    violations += guard_all_numbers_grounded(draft_email.body, fact_sheet)
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
    results = [run_case(case) for case in GOLDEN_SET]
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
```

- [ ] **Step 5: Create the Makefile** — `Makefile` (repo root):
```makefile
.PHONY: test eval

test:
	. .venv/bin/activate && python3 -m pytest -q

eval:
	. .venv/bin/activate && python3 -m evals.run_eval
```

- [ ] **Step 6: Run** `python3 -m pytest -q` → PASS. Then `make eval` → prints 3 PASS
  lines and exits 0 (`echo $?` to confirm).
- [ ] **Step 7: Commit**
```bash
git add evals/fake_llm.py evals/run_eval.py Makefile tests/test_run_eval.py
git commit -m "feat: eval->improve loop (make eval) over the golden set with a deterministic fake LLM"
```

---

### Task 4: Human-feedback flywheel

**Files:**
- Create: `evals/flywheel.py`
- Test: `tests/test_flywheel.py`

**Interfaces:**
- `evals.flywheel.promote_corrections(feedback: FeedbackStore, approval: ApprovalStore, path: Path = DEFAULT_PROMOTED_PATH) -> list[GoldenCase]` —
  reads every correction in `feedback.corrections()`, looks up the underlying
  `Draft` via `approval.get(draft_id)`, derives a `GoldenCase` from its
  `experiment_id` + critical anomalies, and durably persists any NEW case (by
  `experiment_id`) to `evals/promoted_golden_cases.json`. Idempotent: re-running
  with the same corrections promotes nothing new.
- `evals.flywheel.load_promoted_cases(path: Path = DEFAULT_PROMOTED_PATH) -> list[GoldenCase]`
  — for `run_eval.py` to include promoted cases automatically (Task 3's `main()` is
  extended in this task to call `GOLDEN_SET + load_promoted_cases()`).
- **Known limitation (state plainly, do not hide):** a promoted case's
  `expected_fact_keys` defaults to `frozenset()` (conservative) since re-deriving it
  would require re-fetching the original result data, which is out of scope for this
  task — only `expected_critical_rules` is populated from the draft's own recorded
  anomalies.

- [ ] **Step 1: Write the failing test** — `tests/test_flywheel.py`:
```python
from adaptyv.governance.approval import ApprovalStore
from adaptyv.governance.audit import AuditLog
from adaptyv.governance.db import connect
from adaptyv.governance.feedback import FeedbackStore
from adaptyv.governance.models import Actor, AnomalyFinding
from evals.flywheel import load_promoted_cases, promote_corrections

HUMAN = Actor(kind="human", id="alice")
AGENT = Actor(kind="agent", id="watcher")


def _setup():
    conn = connect()
    approval = ApprovalStore(conn, AuditLog(conn))
    feedback = FeedbackStore(conn)
    return approval, feedback


def test_promote_corrections_derives_a_case_from_a_rejected_draft(tmp_path):
    approval, feedback = _setup()
    finding = AnomalyFinding(rule="control_out_of_policy", severity="critical", evidence="e")
    draft = approval.create_draft("exp-promoted-1", "bad body", anomalies=[finding], created_by=AGENT)
    approval.reject(draft.draft_id, HUMAN, note="wrong tone")
    feedback.record_correction(draft.draft_id, "corrected body text", HUMAN)

    path = tmp_path / "promoted.json"
    promoted = promote_corrections(feedback, approval, path=path)

    assert len(promoted) == 1
    assert promoted[0].experiment_id == "exp-promoted-1"
    assert promoted[0].expected_critical_rules == frozenset({"control_out_of_policy"})
    assert path.exists()


def test_promote_corrections_is_idempotent(tmp_path):
    approval, feedback = _setup()
    draft = approval.create_draft("exp-promoted-2", "body", anomalies=[], created_by=AGENT)
    feedback.record_correction(draft.draft_id, "corrected", HUMAN)
    path = tmp_path / "promoted.json"

    first = promote_corrections(feedback, approval, path=path)
    second = promote_corrections(feedback, approval, path=path)

    assert len(first) == 1
    assert len(second) == 0  # nothing new to promote
    assert len(load_promoted_cases(path)) == 1


def test_load_promoted_cases_returns_empty_list_when_file_absent(tmp_path):
    assert load_promoted_cases(tmp_path / "does_not_exist.json") == []
```

- [ ] **Step 2: Run** → FAIL (`ModuleNotFoundError: No module named 'evals.flywheel'`).

- [ ] **Step 3: Implement** — `evals/flywheel.py`:
```python
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
```

- [ ] **Step 4: Wire promoted cases into the eval loop.** In `evals/run_eval.py`,
  import `load_promoted_cases` and change `main()`'s first line to:
```python
    results = [run_case(case) for case in GOLDEN_SET + load_promoted_cases()]
```
  (Add `from evals.flywheel import load_promoted_cases` to the imports.)

- [ ] **Step 5: Run** `python3 -m pytest -q` → PASS (all prior + new). Also re-run
  `make eval` to confirm it still passes with zero promoted cases present (the default
  `evals/promoted_golden_cases.json` doesn't exist yet in the repo, so
  `load_promoted_cases()` returns `[]` and behavior is unchanged).
- [ ] **Step 6: Commit**
```bash
git add evals/flywheel.py evals/run_eval.py tests/test_flywheel.py
git commit -m "feat: human-feedback flywheel (promote corrected drafts into the golden set)"
```

---

### Task 5: Autonomous watch loop (`adaptyv watch`)

**Files:**
- Create: `adaptyv/agents/stub.py` (extracted, now-public `StubEmailDrafter`)
- Modify: `adaptyv/bridge.py` (import the extracted stub instead of defining its own)
- Modify: `adaptyv/cli.py` (add the `watch` command)
- Test: `tests/test_stub_drafter.py`, `tests/test_cli_watch.py`

**Interfaces:**
- `adaptyv.agents.stub.StubEmailDrafter` — the exact same zero-credential,
  deterministic drafter previously private to `adaptyv/bridge.py` (`_StubDrafter`),
  now public so both the bridge and the CLI's `watch` command can share it (no
  duplicated logic). `.model = "stub-drafter"`, `.draft(result, findings) ->
  EmailDraftSchema` — behavior is byte-for-byte identical to the old private class.
- `adaptyv/bridge.py`'s `_op_draft_customer_update` now does
  `from adaptyv.agents.stub import StubEmailDrafter` and uses `StubEmailDrafter()`
  instead of its old private class — no behavior change, existing bridge tests must
  still pass unmodified.
- New CLI command: `adaptyv watch [--interval N] [--once] [--mock/--no-mock] [--db PATH]`
  — polls `Watcher.run()` on an `interval`-second loop (default 60s), printing each
  created draft and any `watcher.errors`; `--once` runs a single cycle and exits
  (for testability/cron use) instead of looping forever.

- [ ] **Step 1: Write the failing test for the extraction** — `tests/test_stub_drafter.py`:
```python
from adaptyv.agents.stub import StubEmailDrafter
from adaptyv.governance.models import AnomalyFinding
from adaptyv.models import ResultInfo


def _result():
    return ResultInfo.model_validate({
        "id": "r1", "title": "Affinity results", "experiment_id": "e1",
        "result_type": "affinity", "created_at": "2026-07-20T10:00:00Z",
        "metadata": {}, "summary": []})


def test_stub_drafter_has_model_attribute():
    assert StubEmailDrafter().model == "stub-drafter"


def test_stub_drafter_mentions_findings_in_body():
    finding = AnomalyFinding(rule="all_sequences_failed", severity="critical", evidence="0/2 expressed")
    draft = StubEmailDrafter().draft(_result(), [finding])
    assert "all_sequences_failed" in draft.body
    assert "0/2 expressed" in draft.body


def test_stub_drafter_notes_no_anomalies_when_none_given():
    draft = StubEmailDrafter().draft(_result(), [])
    assert "No anomalies detected" in draft.body
```

- [ ] **Step 2: Run** → FAIL (`ModuleNotFoundError: No module named 'adaptyv.agents.stub'`).

- [ ] **Step 3: Extract** — `adaptyv/agents/stub.py` (byte-identical logic to the
  existing private class in `adaptyv/bridge.py`, just renamed and relocated):
```python
from __future__ import annotations

from adaptyv.agents.email import EmailDraftSchema


class StubEmailDrafter:
    """Zero-credential drafter: no Claude call. Shared by the bridge's default
    draft_customer_update path and the `adaptyv watch` CLI command."""
    model = "stub-drafter"

    def draft(self, result, findings) -> EmailDraftSchema:
        lines = [f"Results are in for {result.title}."]
        for f in findings:
            lines.append(f"[{f.severity.value.upper()}] {f.rule}: {f.evidence}")
        if not findings:
            lines.append("No anomalies detected.")
        return EmailDraftSchema(subject=f"Update: {result.title}", body="\n".join(lines))
```
  In `adaptyv/bridge.py`: remove the private `class _StubDrafter: ...` block entirely,
  add `from adaptyv.agents.stub import StubEmailDrafter` to the imports, and change
  `_op_draft_customer_update`'s `drafter = _StubDrafter()` to
  `drafter = StubEmailDrafter()`. No other change to `bridge.py`.

- [ ] **Step 4: Run** `python3 -m pytest tests/test_stub_drafter.py tests/test_bridge.py -q`
  → PASS (the extraction must not break any existing bridge test).

- [ ] **Step 5: Write the failing test for the CLI command** — `tests/test_cli_watch.py`:
```python
from typer.testing import CliRunner

from adaptyv.cli import app
from adaptyv.governance.approval import ApprovalStore
from adaptyv.governance.audit import AuditLog
from adaptyv.governance.db import connect

runner = CliRunner()


def test_watch_once_drafts_and_reports(tmp_path):
    db = str(tmp_path / "gov.db")
    result = runner.invoke(app, ["watch", "--once", "--db", db])
    assert result.exit_code == 0
    assert "drafted:" in result.stdout


def test_watch_once_is_idempotent_across_invocations(tmp_path):
    db = str(tmp_path / "gov.db")
    runner.invoke(app, ["watch", "--once", "--db", db])
    second = runner.invoke(app, ["watch", "--once", "--db", db])
    assert second.exit_code == 0
    conn = connect(db)
    store = ApprovalStore(conn, AuditLog(conn))
    first_count = len(store.list())
    runner.invoke(app, ["watch", "--once", "--db", db])
    assert len(store.list()) == first_count  # no new drafts on the third run
```

- [ ] **Step 6: Run** → FAIL (`no such command 'watch'`).

- [ ] **Step 7: Implement.** Add to `adaptyv/cli.py` (imports at top, command
  alongside the existing `review`/`audit` commands):
```python
import time

from adaptyv.agents.anomaly import AnomalyDetector
from adaptyv.agents.policy import DEFAULT_POLICY
from adaptyv.agents.stub import StubEmailDrafter
from adaptyv.agents.watcher import Watcher
```
```python
@app.command("watch")
def watch_command(
    interval: int = typer.Option(60, help="Seconds between polling cycles"),
    once: bool = typer.Option(False, help="Run a single cycle and exit"),
    mock: bool = typer.Option(True),
    db: str = typer.Option("adaptyv_governance.db"),
):
    """Poll for newly-completed experiments and draft customer updates."""
    client = _c(mock)
    conn = connect(db)
    store = ApprovalStore(conn, AuditLog(conn))
    watcher = Watcher(client, AnomalyDetector(DEFAULT_POLICY), StubEmailDrafter(), store, conn)
    while True:
        drafts = watcher.run()
        for d in drafts:
            typer.echo(f"drafted: {d.draft_id} ({d.experiment_id})")
        for experiment_id, result_id, exc in watcher.errors:
            typer.echo(f"error: {experiment_id}/{result_id}: {exc}", err=True)
        if once:
            break
        time.sleep(interval)
```

- [ ] **Step 8: Run** `python3 -m pytest -q` → PASS (all prior + new).
- [ ] **Step 9: Commit**
```bash
git add adaptyv/agents/stub.py adaptyv/bridge.py adaptyv/cli.py tests/test_stub_drafter.py tests/test_cli_watch.py
git commit -m "feat: adaptyv watch CLI (autonomous polling loop over the idempotent Watcher)"
```

---

## Phase 5 Definition of Done

- `python3 -m pytest -q` fully green (all prior phases + eval suite tests).
- `make eval` runs the real golden set through the real `EmailDrafter`/`substitute_facts`
  path with zero network calls, prints a PASS/FAIL report, and exits 0.
- Every deterministic guard genuinely fails when its condition is violated (proven by
  the guard unit tests, not just the happy path).
- The flywheel promotes a real rejected+corrected draft into a durable golden case,
  is idempotent, and `run_eval.py` picks up promoted cases automatically.
- `adaptyv watch --once` runs a full detect→draft→PENDING_REVIEW cycle and is
  idempotent across repeated invocations (reusing Phase 3's durable idempotency key
  — no new logic needed for this guarantee).
- `StubEmailDrafter` has exactly one implementation, shared by the bridge and the CLI.

**Explicitly out of scope this phase:** the LLM-judge (accuracy/completeness/tone
rubric scoring via a real Anthropic call) — reserved for a future phase/decision since
it requires live API credentials and incurs token cost, per the user's explicit scope
choice.

**Next (Phase 6, written just-in-time):** polish — README, architecture diagram,
finalizing LEARNING_GUIDE, a Loom demo script, and (stretch) TestPyPI packaging.
