# Phase 3 — ExperimentWatcher Agent — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the ExperimentWatcher agent — a versioned, policy-driven `AnomalyDetector`; a Claude-powered `EmailDrafter` that never emits raw numbers itself (placeholder-substitution only); and a `Watcher` that turns completed experiment results into `PENDING_REVIEW` drafts through Phase 2's `ApprovalStore`, with a durable idempotency key so restarts and re-runs never duplicate drafts.

**Architecture:** `adaptyv/agents/` is a new package that *consumes* Phase 1 (`AdaptyvClient`, `ResultInfo`/`AffinityResultSummary`) and Phase 2 (`ApprovalStore`, `Actor`, `AnomalyFinding`, `AnomalySeverity`) without modifying either. Detection (deterministic, policy-driven) is fully separated from drafting (LLM, fact-injected): the detector never calls Claude, and the drafter never decides severity. The drafter uses Anthropic's structured-outputs (`client.messages.parse`) to get a typed `{subject, body}` response where `body` contains `{{fact_id}}` tokens; a deterministic substitution step replaces every token with a pre-computed, validated value and raises if any token is unresolved. The `Watcher` persists a `(experiment_id, result_id, drafter_model)` idempotency key in its own sqlite table (same `db.connect` helper as governance) so a result is never drafted twice.

**Tech Stack:** Python 3.11+, pydantic v2, `anthropic` SDK (`client.messages.parse`, structured outputs), stdlib `sqlite3`, pytest.

## Global Constraints

- Python 3.11+, sync only, pydantic v2. Work inside the repo-local venv (`. .venv/bin/activate`); use `python3 -m pytest`.
- **No live API calls in tests.** `EmailDrafter` takes an injected `client` (Anthropic SDK client or a test double); tests inject a fake object exposing `.messages.parse(...)` — never call the real network.
- Model constant: `EMAIL_DRAFT_MODEL = "claude-opus-4-8"` (module-level, in `adaptyv/agents/email.py`) — the current default per the `claude-api` skill; do not hardcode a different or dated model ID.
- New agent exceptions extend `adaptyv.errors.AdaptyvError` via a new `AgentError` base (parallel to `GovernanceError`).
- The detector is pure and deterministic: same `(result, policy)` in → same findings out, no randomness, no I/O.
- The drafter never sources a number itself — every number in the output body must arrive via `{{fact_id}}` substitution from a fact sheet built by our own code.
- TDD: failing test first (fails for the real reason, deps already installed), then minimal code, green, commit.
- Commit messages exactly as written below; **NO `Co-Authored-By`/`Generated with` trailer**. Commit only each task's own files with explicit `git add <paths>` (never `-A`/`-am`); do **not** touch `ROADMAP.md`/docs in task commits.
- End every task with `python3 -m pytest -q` fully green, output pristine.

---

### Task 1: Versioned anomaly policy

**Files:**
- Create: `adaptyv/agents/__init__.py`
- Create: `adaptyv/agents/policy.py`
- Test: `tests/test_anomaly_policy.py`

**Interfaces:**
- Produces `adaptyv.agents.policy.AnomalyPolicy` (pydantic, `extra="forbid"`):
  `version: str`, `positive_control_kd_min: float`, `positive_control_kd_max: float`,
  `kd_plausible_min: float`, `kd_plausible_max: float`, `min_replicates: int`.
- `DEFAULT_POLICY: AnomalyPolicy` — a sensible v0 instance (documented rationale in a comment: Kd in molar units, so `1e-12`–`1e-6` covers pM–µM binders; positive control expected `1e-11`–`1e-7`; `min_replicates=2`).

- [ ] **Step 1: Write the failing test** — `tests/test_anomaly_policy.py`:
```python
from adaptyv.agents.policy import AnomalyPolicy, DEFAULT_POLICY


def test_default_policy_has_sane_bounds():
    assert DEFAULT_POLICY.version == "v0"
    assert DEFAULT_POLICY.kd_plausible_min < DEFAULT_POLICY.kd_plausible_max
    assert DEFAULT_POLICY.positive_control_kd_min < DEFAULT_POLICY.positive_control_kd_max
    assert DEFAULT_POLICY.min_replicates >= 1


def test_policy_is_strict():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        AnomalyPolicy(version="v0", positive_control_kd_min=1e-11,
                      positive_control_kd_max=1e-7, kd_plausible_min=1e-12,
                      kd_plausible_max=1e-6, min_replicates=2, unexpected_field=1)


def test_policy_is_versionable():
    custom = AnomalyPolicy(version="v1-strict", positive_control_kd_min=1e-10,
                           positive_control_kd_max=1e-8, kd_plausible_min=1e-11,
                           kd_plausible_max=1e-7, min_replicates=3)
    assert custom.version == "v1-strict" and custom.min_replicates == 3
```

- [ ] **Step 2: Run** `python3 -m pytest tests/test_anomaly_policy.py -q` → FAIL (`ModuleNotFoundError: adaptyv.agents.policy`).

- [ ] **Step 3: Implement.** `adaptyv/agents/__init__.py`: (empty file).
  `adaptyv/agents/policy.py`:
```python
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class AnomalyPolicy(BaseModel):
    """Versioned, explicit thresholds for anomaly detection — an input, not a
    hardcoded constant, because the OpenAPI result schema carries no
    authoritative 'expected range' for a positive control or a plausible Kd."""
    model_config = ConfigDict(extra="forbid")

    version: str
    positive_control_kd_min: float
    positive_control_kd_max: float
    kd_plausible_min: float
    kd_plausible_max: float
    min_replicates: int


# v0 rationale: Kd is in molar units. Typical antibody/binder affinities span
# ~1pM-1uM; a positive control (a known-good binder) is expected tighter,
# ~10pM-100nM. min_replicates=2 is the minimum for any statistical confidence.
DEFAULT_POLICY = AnomalyPolicy(
    version="v0",
    positive_control_kd_min=1e-11,
    positive_control_kd_max=1e-7,
    kd_plausible_min=1e-12,
    kd_plausible_max=1e-6,
    min_replicates=2,
)
```

- [ ] **Step 4: Run** → PASS. **Step 5: Commit**
```bash
git add adaptyv/agents/__init__.py adaptyv/agents/policy.py tests/test_anomaly_policy.py
git commit -m "feat: versioned anomaly policy (explicit thresholds, not hardcoded)"
```

---

### Task 2: Deterministic AnomalyDetector

**Files:**
- Create: `adaptyv/agents/anomaly.py`
- Modify: `adaptyv/errors.py` (add `AgentError` base)
- Test: `tests/test_anomaly_detector.py`

**Interfaces:**
- Consumes: `adaptyv.models.{ResultInfo, AffinityResultSummary}` (Phase 1),
  `adaptyv.governance.models.{AnomalyFinding, AnomalySeverity}` (Phase 2),
  `adaptyv.agents.policy.AnomalyPolicy` (Task 1).
- Produces: `adaptyv.agents.anomaly.AnomalyDetector(policy: AnomalyPolicy)` with
  `detect(result: ResultInfo) -> list[AnomalyFinding]`.
- Adds `AgentError(AdaptyvError)` to `adaptyv/errors.py` (used by Task 4).

- [ ] **Step 1: Write the failing test** — `tests/test_anomaly_detector.py`:
```python
from adaptyv.agents.anomaly import AnomalyDetector
from adaptyv.agents.policy import AnomalyPolicy
from adaptyv.governance.models import AnomalySeverity
from adaptyv.models import ResultInfo

POLICY = AnomalyPolicy(version="test", positive_control_kd_min=1e-11,
                       positive_control_kd_max=1e-7, kd_plausible_min=1e-12,
                       kd_plausible_max=1e-6, min_replicates=2)


def _result(summary):
    return ResultInfo.model_validate({
        "id": "r1", "title": "t", "experiment_id": "e1", "result_type": "affinity",
        "created_at": "2026-07-20T10:00:00Z", "metadata": {}, "summary": summary})


def _affinity(name, kd_mean=None, positive_control=False, replicates=None):
    return {"result_type": "affinity", "sequence": {"aa_string": "MKAA", "name": name},
            "kd_units": "M", "binding_strength": "strong", "positive_control": positive_control,
            "performance": {}, "kd_mean": kd_mean, "replicates": replicates or []}


def test_all_failed_is_critical():
    result = _result([_affinity("b1", kd_mean=None), _affinity("b2", kd_mean=None)])
    findings = AnomalyDetector(POLICY).detect(result)
    crit = [f for f in findings if f.rule == "all_sequences_failed"]
    assert len(crit) == 1 and crit[0].severity is AnomalySeverity.CRITICAL
    assert set(crit[0].affected_ids) == {"b1", "b2"}


def test_healthy_result_has_no_critical():
    result = _result([
        _affinity("b1", kd_mean=1e-9, replicates=[{"replicate": 1}, {"replicate": 2}]),
        _affinity("ctrl", kd_mean=2e-9, positive_control=True,
                  replicates=[{"replicate": 1}, {"replicate": 2}]),
    ])
    findings = AnomalyDetector(POLICY).detect(result)
    assert not any(f.severity is AnomalySeverity.CRITICAL for f in findings)


def test_control_out_of_policy_is_critical():
    result = _result([
        _affinity("b1", kd_mean=1e-9, replicates=[{"replicate": 1}, {"replicate": 2}]),
        _affinity("ctrl", kd_mean=1e-3, positive_control=True,
                  replicates=[{"replicate": 1}, {"replicate": 2}]),
    ])
    findings = AnomalyDetector(POLICY).detect(result)
    crit = [f for f in findings if f.rule == "control_out_of_policy"]
    assert len(crit) == 1 and crit[0].severity is AnomalySeverity.CRITICAL
    assert crit[0].affected_ids == ["ctrl"]
    assert crit[0].policy_version == "test"


def test_kd_out_of_bounds_is_warning():
    result = _result([_affinity("b1", kd_mean=1.0,
                                replicates=[{"replicate": 1}, {"replicate": 2}])])
    findings = AnomalyDetector(POLICY).detect(result)
    warn = [f for f in findings if f.rule == "kd_out_of_bounds"]
    assert len(warn) == 1 and warn[0].severity is AnomalySeverity.WARNING


def test_missing_replicates_is_warning():
    result = _result([_affinity("b1", kd_mean=1e-9, replicates=[{"replicate": 1}])])
    findings = AnomalyDetector(POLICY).detect(result)
    warn = [f for f in findings if f.rule == "missing_replicates"]
    assert len(warn) == 1 and warn[0].affected_ids == ["b1"]


def test_deterministic_same_input_same_output():
    result = _result([_affinity("b1", kd_mean=None)])
    d = AnomalyDetector(POLICY)
    assert d.detect(result) == d.detect(result)
```

- [ ] **Step 2: Run** → FAIL (`ModuleNotFoundError: adaptyv.agents.anomaly`).

- [ ] **Step 3: Add `AgentError`** to `adaptyv/errors.py` (append after the governance exceptions block):
```python
class AgentError(AdaptyvError): ...
```

- [ ] **Step 4: Implement** — `adaptyv/agents/anomaly.py`:
```python
from __future__ import annotations

from adaptyv.agents.policy import AnomalyPolicy
from adaptyv.governance.models import AnomalyFinding
from adaptyv.models import AffinityResultSummary, ResultInfo


def _label(s: AffinityResultSummary) -> str:
    return s.sequence.name or s.sequence.aa_string[:8]


class AnomalyDetector:
    """Pure, deterministic. Never calls Claude; never does I/O."""

    def __init__(self, policy: AnomalyPolicy) -> None:
        self._policy = policy

    def detect(self, result: ResultInfo) -> list[AnomalyFinding]:
        affinity = [s for s in result.summary if isinstance(s, AffinityResultSummary)]
        findings: list[AnomalyFinding] = []
        findings.extend(self._all_failed(affinity))
        findings.extend(self._control_out_of_policy(affinity))
        findings.extend(self._kd_out_of_bounds(affinity))
        findings.extend(self._missing_replicates(affinity))
        return findings

    def _all_failed(self, affinity: list[AffinityResultSummary]) -> list[AnomalyFinding]:
        non_control = [s for s in affinity if not s.positive_control]
        if non_control and all(s.kd_mean is None for s in non_control):
            ids = [_label(s) for s in non_control]
            return [AnomalyFinding(
                rule="all_sequences_failed", severity="critical",
                evidence=f"0/{len(non_control)} non-control sequences showed measurable binding (kd_mean unset)",
                affected_ids=ids, policy_version=self._policy.version)]
        return []

    def _control_out_of_policy(self, affinity: list[AffinityResultSummary]) -> list[AnomalyFinding]:
        out = []
        for s in affinity:
            if s.positive_control and s.kd_mean is not None:
                if not (self._policy.positive_control_kd_min <= s.kd_mean <= self._policy.positive_control_kd_max):
                    out.append(AnomalyFinding(
                        rule="control_out_of_policy", severity="critical",
                        evidence=(f"positive control kd_mean={s.kd_mean:.2e} {s.kd_units} outside "
                                 f"policy range [{self._policy.positive_control_kd_min:.2e}, "
                                 f"{self._policy.positive_control_kd_max:.2e}]"),
                        affected_ids=[_label(s)], policy_version=self._policy.version))
        return out

    def _kd_out_of_bounds(self, affinity: list[AffinityResultSummary]) -> list[AnomalyFinding]:
        out = []
        for s in affinity:
            if not s.positive_control and s.kd_mean is not None:
                if not (self._policy.kd_plausible_min <= s.kd_mean <= self._policy.kd_plausible_max):
                    out.append(AnomalyFinding(
                        rule="kd_out_of_bounds", severity="warning",
                        evidence=(f"{_label(s)} kd_mean={s.kd_mean:.2e} {s.kd_units} outside plausible "
                                 f"range [{self._policy.kd_plausible_min:.2e}, {self._policy.kd_plausible_max:.2e}]"),
                        affected_ids=[_label(s)], policy_version=self._policy.version))
        return out

    def _missing_replicates(self, affinity: list[AffinityResultSummary]) -> list[AnomalyFinding]:
        out = []
        for s in affinity:
            if len(s.replicates) < self._policy.min_replicates:
                out.append(AnomalyFinding(
                    rule="missing_replicates", severity="warning",
                    evidence=f"{_label(s)} has {len(s.replicates)} replicate(s), policy requires "
                            f"{self._policy.min_replicates}",
                    affected_ids=[_label(s)], policy_version=self._policy.version))
        return out
```

- [ ] **Step 5: Run** `python3 -m pytest -q` → PASS (all prior + new). **Step 6: Commit**
```bash
git add adaptyv/agents/anomaly.py adaptyv/errors.py tests/test_anomaly_detector.py
git commit -m "feat: deterministic policy-driven AnomalyDetector"
```

---

### Task 3: Anomalous affinity fixtures

**Files:**
- Modify: `adaptyv/mocks/fixtures/experiments_list.json` (add 2 experiments, additive)
- Modify: `adaptyv/mocks/fixtures/results_list.json` (add 2 results, additive)
- Test: `tests/test_anomalous_fixtures.py`

**Interfaces:** No new Python interfaces — this task only adds mock demo data so the
Watcher (Task 5) and a future Loom demo have real anomaly scenarios to show.
- `EXP-1003` ("All-sequences-failed panel", status `done`) with a result whose every
  non-control summary has `kd_mean: null`.
- `EXP-1004` ("Control-out-of-range panel", status `done`) with a result whose
  positive-control summary has an implausible `kd_mean` (e.g. `1e-3`, far outside any
  sane policy range) and at least one healthy non-control summary.

- [ ] **Step 1: Write the failing test** — `tests/test_anomalous_fixtures.py`:
```python
from adaptyv import AdaptyvClient
from adaptyv.agents.anomaly import AnomalyDetector
from adaptyv.agents.policy import DEFAULT_POLICY
from adaptyv.governance.models import AnomalySeverity


def test_all_failed_fixture_trips_critical():
    client = AdaptyvClient(mock=True)
    results = client.experiments.results("33333333-3333-3333-3333-333333333333")
    findings = AnomalyDetector(DEFAULT_POLICY).detect(results[0])
    assert any(f.rule == "all_sequences_failed" and f.severity is AnomalySeverity.CRITICAL
              for f in findings)


def test_control_out_of_range_fixture_trips_critical():
    client = AdaptyvClient(mock=True)
    results = client.experiments.results("44444444-4444-4444-4444-444444444444")
    findings = AnomalyDetector(DEFAULT_POLICY).detect(results[0])
    assert any(f.rule == "control_out_of_policy" and f.severity is AnomalySeverity.CRITICAL
              for f in findings)


def test_existing_experiments_still_present():
    exps = AdaptyvClient(mock=True).experiments.list()
    codes = {e.code for e in exps}
    assert {"EXP-1001", "EXP-1002", "EXP-1003", "EXP-1004"} <= codes
```

- [ ] **Step 2: Run** → FAIL (unknown experiment id / no matching fixtures yet).

- [ ] **Step 3: Extend the fixtures — ADD entries, do not remove or reorder existing ones.**
  In `adaptyv/mocks/fixtures/experiments_list.json`, append to the `items` array (keep
  the existing 2 entries and update `total`/`count` to 4):
```json
  ,
  {"id": "33333333-3333-3333-3333-333333333333", "code": "EXP-1003", "status": "done",
   "results_status": "all", "created_at": "2026-07-18T10:00:00Z",
   "experiment_url": "https://devs.adaptyvbio.com/e/EXP-1003", "experiment_type": "affinity",
   "name": "All-sequences-failed panel"},
  {"id": "44444444-4444-4444-4444-444444444444", "code": "EXP-1004", "status": "done",
   "results_status": "all", "created_at": "2026-07-19T10:00:00Z",
   "experiment_url": "https://devs.adaptyvbio.com/e/EXP-1004", "experiment_type": "affinity",
   "name": "Control-out-of-range panel"}
```
  (Update `"total": 2, "count": 2` → `"total": 4, "count": 4`.)

  In `adaptyv/mocks/fixtures/results_list.json`, append to the `items` array (update
  `total`/`count` to 3):
```json
  ,
  {"id": "aaaaaaaa-0000-0000-0000-000000000002", "title": "Affinity results — All-sequences-failed panel",
   "experiment_id": "33333333-3333-3333-3333-333333333333", "result_type": "affinity",
   "created_at": "2026-07-18T12:00:00Z", "metadata": {},
   "summary": [
     {"result_type": "affinity", "sequence": {"aa_string": "MKCC", "name": "binder-3"},
      "kd_units": "M", "binding_strength": "none", "positive_control": false,
      "performance": {"verdict": "fail"}, "kd_mean": null,
      "replicates": [{"replicate": 1, "expression": "none"}, {"replicate": 2, "expression": "none"}]},
     {"result_type": "affinity", "sequence": {"aa_string": "MKDD", "name": "binder-4"},
      "kd_units": "M", "binding_strength": "none", "positive_control": false,
      "performance": {"verdict": "fail"}, "kd_mean": null,
      "replicates": [{"replicate": 1, "expression": "none"}, {"replicate": 2, "expression": "none"}]}
   ]},
  {"id": "aaaaaaaa-0000-0000-0000-000000000003", "title": "Affinity results — Control-out-of-range panel",
   "experiment_id": "44444444-4444-4444-4444-444444444444", "result_type": "affinity",
   "created_at": "2026-07-19T12:00:00Z", "metadata": {},
   "summary": [
     {"result_type": "affinity", "sequence": {"aa_string": "MKEE", "name": "binder-5"},
      "kd_units": "M", "binding_strength": "strong", "positive_control": false,
      "performance": {"verdict": "pass"}, "kd_mean": 1.5e-9,
      "replicates": [{"replicate": 1, "kd": 1.4e-9}, {"replicate": 2, "kd": 1.6e-9}]},
     {"result_type": "affinity", "sequence": {"aa_string": "CTRLQ", "name": "pos-control"},
      "kd_units": "M", "binding_strength": "weak", "positive_control": true,
      "performance": {"verdict": "out_of_range"}, "kd_mean": 1e-3,
      "replicates": [{"replicate": 1, "kd": 1e-3}, {"replicate": 2, "kd": 1.1e-3}]}
   ]}
```
  (Update `"total": 1, "count": 1` → `"total": 3, "count": 3`.)

- [ ] **Step 4: Run** `python3 -m pytest -q` → PASS (all prior tests still green — this
  is the critical regression check, since the fixtures are shared). **Step 5: Commit**
```bash
git add adaptyv/mocks/fixtures/experiments_list.json adaptyv/mocks/fixtures/results_list.json tests/test_anomalous_fixtures.py
git commit -m "feat: add all-failed and control-out-of-range demo fixtures"
```

---

### Task 4: EmailDrafter (Claude, placeholder-substitution)

**Files:**
- Create: `adaptyv/agents/email.py`
- Modify: `adaptyv/errors.py` (add `UnresolvedPlaceholderError(AgentError)`)
- Test: `tests/test_email_drafter.py`

**Interfaces:**
- Adds `UnresolvedPlaceholderError(AgentError)` to `adaptyv/errors.py`.
- Produces `adaptyv.agents.email`:
  - `EMAIL_DRAFT_MODEL = "claude-opus-4-8"` (module constant).
  - `EmailDraftSchema(pydantic.BaseModel)`: `subject: str`, `body: str`.
  - `build_fact_sheet(result: ResultInfo) -> dict[str, str]` — pure; one entry per
    non-null `kd_mean` on an `AffinityResultSummary`, keyed `kd_mean_<slug>`.
  - `substitute_facts(body: str, fact_sheet: dict[str, str]) -> str` — replaces every
    `{{fact_id}}`; raises `UnresolvedPlaceholderError` if a token isn't in `fact_sheet`.
  - `EmailDrafter(client, model: str = EMAIL_DRAFT_MODEL)` with
    `draft(result: ResultInfo, findings: list[AnomalyFinding]) -> EmailDraftSchema`
    (returns a schema whose `.body` has already been substituted — no `{{...}}` remains).

- [ ] **Step 1: Write the failing test** — `tests/test_email_drafter.py`:
```python
from types import SimpleNamespace

import pytest

from adaptyv.agents.email import (EmailDrafter, EmailDraftSchema, build_fact_sheet,
                                  substitute_facts)
from adaptyv.errors import UnresolvedPlaceholderError
from adaptyv.governance.models import AnomalyFinding
from adaptyv.models import ResultInfo


def _result():
    return ResultInfo.model_validate({
        "id": "r1", "title": "Affinity results", "experiment_id": "e1",
        "result_type": "affinity", "created_at": "2026-07-20T10:00:00Z", "metadata": {},
        "summary": [
            {"result_type": "affinity", "sequence": {"aa_string": "MKAA", "name": "binder-1"},
             "kd_units": "M", "binding_strength": "strong", "positive_control": False,
             "performance": {"verdict": "pass"}, "kd_mean": 1.2e-9, "replicates": []},
        ]})


def test_build_fact_sheet_has_kd_mean_entry():
    facts = build_fact_sheet(_result())
    assert facts["kd_mean_binder-1"] == "1.20e-09 M"


def test_substitute_facts_replaces_token():
    out = substitute_facts("Kd was {{kd_mean_binder-1}}.", {"kd_mean_binder-1": "1.20e-09 M"})
    assert out == "Kd was 1.20e-09 M."


def test_substitute_facts_raises_on_unresolved_token():
    with pytest.raises(UnresolvedPlaceholderError):
        substitute_facts("Kd was {{kd_mean_unknown}}.", {"kd_mean_binder-1": "1.20e-09 M"})


class _FakeParseResponse:
    def __init__(self, parsed_output):
        self.parsed_output = parsed_output


class _FakeMessages:
    def __init__(self, response):
        self._response = response
        self.calls = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


class _FakeClient:
    def __init__(self, response):
        self.messages = _FakeMessages(response)


def test_drafter_substitutes_placeholder_from_model_output():
    fake_response = _FakeParseResponse(EmailDraftSchema(
        subject="Your results are ready",
        body="Binder-1 showed strong binding with Kd {{kd_mean_binder-1}}."))
    client = _FakeClient(fake_response)
    drafter = EmailDrafter(client=client)

    out = drafter.draft(_result(), findings=[])

    assert "{{" not in out.body
    assert "1.20e-09 M" in out.body
    assert client.messages.parse.__self__.calls[0]["output_format"] is EmailDraftSchema


def test_drafter_raises_if_model_emits_unknown_placeholder():
    fake_response = _FakeParseResponse(EmailDraftSchema(
        subject="s", body="Value: {{not_a_real_fact}}"))
    drafter = EmailDrafter(client=_FakeClient(fake_response))
    with pytest.raises(UnresolvedPlaceholderError):
        drafter.draft(_result(), findings=[])


def test_drafter_prompt_includes_anomaly_evidence_text():
    fake_response = _FakeParseResponse(EmailDraftSchema(subject="s", body="no tokens here"))
    client = _FakeClient(fake_response)
    drafter = EmailDrafter(client=client)
    finding = AnomalyFinding(rule="kd_out_of_bounds", severity="warning",
                             evidence="binder-1 kd_mean=1.0 outside plausible range")
    drafter.draft(_result(), findings=[finding])
    sent = client.messages.parse.__self__.calls[0]
    joined = str(sent["messages"])
    assert "outside plausible range" in joined
```

- [ ] **Step 2: Run** → FAIL (`ModuleNotFoundError: adaptyv.agents.email`).

- [ ] **Step 3: Add the exception** — append to `adaptyv/errors.py`:
```python
class UnresolvedPlaceholderError(AgentError): ...
```

- [ ] **Step 4: Implement** — `adaptyv/agents/email.py`:
```python
from __future__ import annotations

import re

from pydantic import BaseModel

from adaptyv.errors import UnresolvedPlaceholderError
from adaptyv.governance.models import AnomalyFinding
from adaptyv.models import AffinityResultSummary, ResultInfo

EMAIL_DRAFT_MODEL = "claude-opus-4-8"

_PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")


class EmailDraftSchema(BaseModel):
    subject: str
    body: str


def _slug(name: str) -> str:
    return name.strip()


def build_fact_sheet(result: ResultInfo) -> dict[str, str]:
    """Pure. One entry per non-null kd_mean — the only numbers the drafter may cite."""
    facts: dict[str, str] = {}
    for s in result.summary:
        if isinstance(s, AffinityResultSummary) and s.kd_mean is not None:
            label = _slug(s.sequence.name or s.sequence.aa_string[:8])
            facts[f"kd_mean_{label}"] = f"{s.kd_mean:.2e} {s.kd_units}"
    return facts


def substitute_facts(body: str, fact_sheet: dict[str, str]) -> str:
    def _replace(m: re.Match) -> str:
        fact_id = m.group(1)
        if fact_id not in fact_sheet:
            raise UnresolvedPlaceholderError(
                f"drafter emitted unknown placeholder '{{{{{fact_id}}}}}' — not in the fact sheet")
        return fact_sheet[fact_id]
    return _PLACEHOLDER.sub(_replace, body)


class EmailDrafter:
    def __init__(self, client, model: str = EMAIL_DRAFT_MODEL) -> None:
        self._client = client
        self.model = model  # public: Watcher reads this to build its idempotency key

    def draft(self, result: ResultInfo, findings: list[AnomalyFinding]) -> EmailDraftSchema:
        fact_sheet = build_fact_sheet(result)
        system = (
            "You draft professional, plain-English customer update emails for a protein "
            "validation lab. You may reference numeric results ONLY via the exact "
            "placeholder tokens listed below, written literally as {{token}} in your body "
            "text — never write a number yourself. Use the qualitative details (binding "
            "strength, performance, anomaly notes) directly as given."
        )
        fact_lines = "\n".join(f"- {{{{{fid}}}}}: a binding-affinity (Kd) value" for fid in fact_sheet)
        finding_lines = "\n".join(f"- [{f.severity.value}] {f.rule}: {f.evidence}" for f in findings)
        user = (
            f"Result title: {result.title}\n\n"
            f"Available numeric placeholders:\n{fact_lines or '(none)'}\n\n"
            f"Anomaly findings:\n{finding_lines or '(none)'}\n\n"
            "Write a short customer update email (subject + body) summarizing these results."
        )
        response = self._client.messages.parse(
            model=self.model,
            max_tokens=1024,
            messages=[{"role": "user", "content": user}],
            system=system,
            output_format=EmailDraftSchema,
        )
        draft = response.parsed_output
        resolved_body = substitute_facts(draft.body, fact_sheet)
        return EmailDraftSchema(subject=draft.subject, body=resolved_body)
```

- [ ] **Step 5: Run** `python3 -m pytest -q` → PASS. **Step 6: Commit**
```bash
git add adaptyv/agents/email.py adaptyv/errors.py tests/test_email_drafter.py
git commit -m "feat: EmailDrafter with typed placeholder substitution (no model-sourced numbers)"
```

---

### Task 5: Watcher orchestration with durable idempotency key

**Files:**
- Create: `adaptyv/agents/watcher.py`
- Test: `tests/test_watcher.py`

**Interfaces:**
- Consumes: `AdaptyvClient` (Phase 1), `AnomalyDetector`/`AnomalyPolicy` (Tasks 1–2),
  `EmailDrafter` (Task 4), `ApprovalStore`/`Actor`/`DraftStatus` (Phase 2),
  `adaptyv.governance.db.connect` (Phase 2, reused for the idempotency table).
- Produces `adaptyv.agents.watcher.Watcher(client, detector, drafter, approval_store, conn)`
  with `run(experiment_ids: list[str] | None = None) -> list[Draft]`. A result is
  identified by `f"{experiment_id}:{result.id}:{drafter.model}"`; already-processed keys
  are skipped. `experiment_ids=None` processes every experiment the client returns.

- [ ] **Step 1: Write the failing test** — `tests/test_watcher.py`:
```python
from adaptyv import AdaptyvClient
from adaptyv.agents.anomaly import AnomalyDetector
from adaptyv.agents.email import EmailDraftSchema
from adaptyv.agents.policy import DEFAULT_POLICY
from adaptyv.agents.watcher import Watcher
from adaptyv.governance.approval import ApprovalStore
from adaptyv.governance.audit import AuditLog
from adaptyv.governance.db import connect
from adaptyv.governance.models import DraftStatus


class _FakeDrafter:
    model = "fake-model"

    def draft(self, result, findings):
        return EmailDraftSchema(subject="Your results", body="See attached summary.")


def _make_watcher():
    conn = connect()
    store = ApprovalStore(conn, AuditLog(conn))
    watcher = Watcher(AdaptyvClient(mock=True), AnomalyDetector(DEFAULT_POLICY),
                      _FakeDrafter(), store, conn)
    return watcher, store


def test_run_creates_pending_review_drafts_for_all_experiments():
    watcher, store = _make_watcher()
    drafts = watcher.run()
    assert drafts
    assert all(d.status is DraftStatus.PENDING_REVIEW for d in drafts)


def test_all_failed_result_creates_draft_with_critical_anomaly():
    watcher, store = _make_watcher()
    drafts = watcher.run(experiment_ids=["33333333-3333-3333-3333-333333333333"])
    assert len(drafts) == 1
    assert any(a.rule == "all_sequences_failed" for a in drafts[0].anomalies)


def test_rerun_does_not_duplicate_drafts():
    watcher, store = _make_watcher()
    first = watcher.run()
    second = watcher.run()
    assert second == []
    assert len(store.list()) == len(first)


def test_experiment_with_no_results_produces_no_draft():
    watcher, store = _make_watcher()
    drafts = watcher.run(experiment_ids=["22222222-2222-2222-2222-222222222222"])
    assert drafts == []
```

- [ ] **Step 2: Run** → FAIL (`ModuleNotFoundError: adaptyv.agents.watcher`).

- [ ] **Step 3: Implement** — `adaptyv/agents/watcher.py`:
```python
from __future__ import annotations

import sqlite3

from adaptyv.agents.anomaly import AnomalyDetector
from adaptyv.agents.email import EmailDrafter
from adaptyv.governance.approval import ApprovalStore
from adaptyv.governance.models import Actor, Draft


class Watcher:
    def __init__(self, client, detector: AnomalyDetector, drafter: EmailDrafter,
                approval_store: ApprovalStore, conn: sqlite3.Connection) -> None:
        self._client = client
        self._detector = detector
        self._drafter = drafter
        self._store = approval_store
        self._conn = conn
        conn.execute(
            "CREATE TABLE IF NOT EXISTS watcher_processed (key TEXT PRIMARY KEY, draft_id TEXT NOT NULL)"
        )
        conn.commit()

    def run(self, experiment_ids: list[str] | None = None) -> list[Draft]:
        if experiment_ids is None:
            experiment_ids = [e.id for e in self._client.experiments.list()]
        created: list[Draft] = []
        for experiment_id in experiment_ids:
            for result in self._client.experiments.results(experiment_id):
                key = f"{experiment_id}:{result.id}:{self._drafter.model}"
                if self._already_processed(key):
                    continue
                findings = self._detector.detect(result)
                email = self._drafter.draft(result, findings)
                draft = self._store.create_draft(
                    experiment_id, email.body, result_id=result.id, anomalies=findings,
                    created_by=Actor(kind="agent", id="watcher"))
                self._mark_processed(key, draft.draft_id)
                created.append(draft)
        return created

    def _already_processed(self, key: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM watcher_processed WHERE key=?", (key,)).fetchone()
        return row is not None

    def _mark_processed(self, key: str, draft_id: str) -> None:
        self._conn.execute(
            "INSERT INTO watcher_processed (key, draft_id) VALUES (?, ?)", (key, draft_id))
        self._conn.commit()
```

- [ ] **Step 4: Run** `python3 -m pytest -q` → PASS (all prior + new). **Step 5: Commit**
```bash
git add adaptyv/agents/watcher.py tests/test_watcher.py
git commit -m "feat: Watcher orchestration with durable idempotency key"
```

---

## Phase 3 Definition of Done

- `python3 -m pytest -q` fully green (Phase 1 + Phase 2 + agent tests), output pristine.
- `AnomalyDetector` is pure/deterministic and driven entirely by an injectable
  `AnomalyPolicy` (no hardcoded thresholds in the detector itself).
- `EmailDrafter` never places a number in output text except via `{{fact_id}}`
  substitution from a fact sheet built by our own code; an unresolved or unknown
  placeholder raises `UnresolvedPlaceholderError` rather than silently passing through.
- `Watcher.run()` creates `PENDING_REVIEW` drafts through the real Phase 2
  `ApprovalStore` (audited, human-approval-gated, anomaly-hard-blocked) and a second
  `run()` call over the same data creates zero additional drafts.
- No live Anthropic API calls anywhere in the test suite.

**Next (Phase 4, written just-in-time):** the subprocess JSON bridge
(`python -m adaptyv --json`) and the TypeScript MCP server exposing
`draft_customer_update` (and the other curated tools) through it.
