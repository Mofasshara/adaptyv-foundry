# Phase 1 — Adaptyv Python SDK Core — Implementation Plan (v2, schema-corrected)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **v2 note (2026-07-24):** This plan was rewritten after a Codex review proved the
> v1 models were built on a hallucinated schema summary. Every model, enum, and
> envelope below is derived from the **raw** OpenAPI JSON
> (`https://foundry-api-public.adaptyvbio.com/api/v1/openapi.json`, OpenAPI 3.1.0,
> API v0.0.2, sha256 `d3b4828f059ebfb7cf10314bb44125fac735042547250fca3143fa44353652c8`),
> parsed deterministically — not via a summarizing fetch. See
> `feedback_verify_api_schemas_raw` memory.

**Goal:** Build the typed, sync Python SDK core (`adaptyv`) — models faithful to the real
API, pluggable transport with mock mode, paginated read + write resources, live HTTP
transport, and a minimal CLI — so `AdaptyvClient(mock=True)` returns typed lab data with
no API key, and the mock/live shapes are identical.

**Architecture:** Hand-written `httpx` + `pydantic v2`. A `Transport` protocol decouples
the client from I/O; `MockTransport` (fixtures) and `LiveTransport` (real API) return the
**same** JSON shapes, including the `{items,total,count,offset}` pagination envelope. This
SDK is the single source of truth the later MCP (via a subprocess JSON bridge), agent, and
evals all reuse.

**Tech Stack:** Python 3.11+, pydantic v2, httpx, Typer, pytest, respx, jsonschema.

## Global Constraints

- Python **3.11+**. Use `python3`/`python3 -m pip` (the environment exposes `python3`,
  not `python`); do all work inside a venv: `python3 -m venv .venv && . .venv/bin/activate`.
- Import package name **`adaptyv`**; distribution **`adaptyv-foundry-sdk`** (TestPyPI). Never publish to real PyPI.
- Sync only — no `async`.
- pydantic **v2** (`model_validate`, `Field`, `Annotated[... , Field(discriminator=...)]`, `ConfigDict`).
- API base URL default `https://devs.adaptyvbio.com`; paths prefixed `/api/v1`.
- **All list endpoints return `{items, total, count, offset}`** — never a bare array.
- Resource path IDs are **UUIDs** (`/experiments/{experiment_id}` is `format: uuid`).
- Response models use `ConfigDict(extra="ignore")` (forward-compat). Request models are strict.
- Never log or print API keys (`api_key` arg or `ADAPTYV_API_KEY` env only).
- Every task ends green (`python3 -m pytest -q`) and is committed. TDD: failing test → minimal code → green → commit.

---

### Task 1: Scaffolding + vendored spec

**Files:** Create `pyproject.toml`, `adaptyv/__init__.py`, `adaptyv/_version.py`,
`tests/__init__.py`, `tests/test_smoke.py`, `tests/data/openapi.json`, `README.md`.

**Interfaces:** Produces importable `adaptyv` exposing `__version__: str`; a pinned
`tests/data/openapi.json` for the contract test.

- [ ] **Step 1: Failing test** — `tests/test_smoke.py`:
```python
import adaptyv

def test_package_exposes_version():
    assert isinstance(adaptyv.__version__, str) and adaptyv.__version__
```
- [ ] **Step 2: Run** `python3 -m pytest tests/test_smoke.py -q` → FAIL (`ModuleNotFoundError`).
- [ ] **Step 3: `pyproject.toml`:**
```toml
[project]
name = "adaptyv-foundry-sdk"
version = "0.1.0"
description = "Typed Python SDK for the Adaptyv Foundry lab API (unofficial)."
requires-python = ">=3.11"
readme = "README.md"
dependencies = ["httpx>=0.27", "pydantic>=2.7", "typer>=0.12"]

[project.optional-dependencies]
dev = ["pytest>=8", "respx>=0.21", "jsonschema>=4.21", "fastapi>=0.110", "anthropic>=0.40"]

[project.scripts]
adaptyv = "adaptyv.cli:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["adaptyv"]

[tool.pytest.ini_options]
addopts = "-q"
markers = ["live_llm: needs ANTHROPIC_API_KEY"]
```
- [ ] **Step 4: Package files.** `adaptyv/_version.py`: `__version__ = "0.1.0"`.
  `adaptyv/__init__.py`:
```python
from adaptyv._version import __version__
__all__ = ["__version__"]
```
  `tests/__init__.py`: empty. `README.md`: one line.
- [ ] **Step 5: Vendor the pinned spec (for the contract test):**
```bash
mkdir -p tests/data
curl -s -o tests/data/openapi.json https://foundry-api-public.adaptyvbio.com/api/v1/openapi.json
python3 -c "import hashlib;print(hashlib.sha256(open('tests/data/openapi.json','rb').read()).hexdigest())"
# expect: d3b4828f059ebfb7cf10314bb44125fac735042547250fca3143fa44353652c8
```
- [ ] **Step 6: Install + run** `python3 -m pip install -e ".[dev]" && python3 -m pytest -q` → PASS.
- [ ] **Step 7: Commit** `git add -A && git commit -m "feat: scaffold adaptyv SDK + vendor pinned OpenAPI spec"`.

---

### Task 2: Models (schema-faithful)

**Files:** Create `adaptyv/models.py`; Test `tests/test_models.py`.

**Interfaces:** Produces from `adaptyv.models`:
- Enums: `ExperimentStatus`, `ResultsStatus`, `ExperimentType`, `Method`, `SequenceType`.
- `Page[T]` generic (`items,total,count,offset`).
- Result cluster: `KineticInterval`, `AffinityReplicate`, `AffinityResult`, `ThermostabilityResult`,
  discriminated `ResultSummary` (on `result_type`), `ResultInfo`.
- Experiment: `TargetReference`, `ExperimentSpecInfo`, `ExpInfo` (detail), `ExperimentListItem` (list).
- Sequence: `SequenceEntry`, `SequenceExperimentRef`, `SequenceInfo` (detail), `SequenceListItem` (list),
  `SequenceAddRequest`, `SequenceAddResponse`.
- Target: `TargetInfo`.
- Create/estimate: `ExperimentSpec`, `CreateExpRequest`, `CreateExpResponse`,
  `CostEstimateRequest`, `CostEstimateResponse`.
- `ErrorResponse` (`error`, `request_id` only), `WhoAmIResponse`.

- [ ] **Step 1: Failing test** — `tests/test_models.py`:
```python
from adaptyv.models import (
    AffinityResult, ExperimentStatus, ExpInfo, ExperimentListItem,
    KineticInterval, Page, ResultInfo, SequenceInfo,
)

def test_status_enum_matches_real_spec():
    assert ExperimentStatus.DONE.value == "done"
    assert {s.value for s in ExperimentStatus} == {
        "draft", "waiting_for_confirmation", "canceled", "waiting_for_materials",
        "in_production", "quote_sent", "in_queue", "data_analysis", "in_review", "done"}

def test_kinetic_interval_bounds_nullable():
    ki = KineticInterval.model_validate({"value": 1.2e-9})
    assert ki.value == 1.2e-9 and ki.ci_low is None and ki.ci_high is None

def test_affinity_result_sequence_is_object_and_performance_is_mapping():
    ar = AffinityResult.model_validate({
        "sequence": {"aa_string": "MKAA"}, "kd_units": "M", "binding_strength": "strong",
        "positive_control": False, "performance": {"verdict": "pass"}, "replicates": []})
    assert ar.sequence.aa_string == "MKAA"
    assert ar.performance == {"verdict": "pass"} and ar.kd_mean is None

def test_result_summary_discriminates_on_result_type():
    ri = ResultInfo.model_validate({
        "id": "22222222-2222-2222-2222-222222222222", "title": "Affinity",
        "experiment_id": "11111111-1111-1111-1111-111111111111", "result_type": "affinity",
        "created_at": "2026-07-20T10:00:00Z", "metadata": {},
        "summary": [{"result_type": "affinity", "sequence": {"aa_string": "MKAA"},
                     "kd_units": "M", "binding_strength": "strong", "positive_control": True,
                     "performance": {"verdict": "pass"}, "replicates": [], "kd_mean": 2.0e-9}]})
    s = ri.summary[0]
    assert s.result_type == "affinity" and s.positive_control is True and s.kd_mean == 2.0e-9

def test_expinfo_requires_experiment_spec_but_listitem_does_not():
    common = dict(id="11111111-1111-1111-1111-111111111111", code="EXP-1001",
                  status="done", results_status="all", created_at="2026-07-01T10:00:00Z",
                  experiment_url="https://devs.adaptyvbio.com/e/EXP-1001")
    li = ExperimentListItem.model_validate(common)          # no experiment_spec -> ok
    assert li.status is ExperimentStatus.DONE
    exp = ExpInfo.model_validate({**common, "experiment_spec": {"experiment_type": "affinity"}})
    assert exp.experiment_spec.experiment_type.value == "affinity"

def test_page_generic():
    p = Page[ExperimentListItem].model_validate(
        {"items": [], "total": 0, "count": 0, "offset": 0})
    assert p.total == 0 and p.items == []

def test_sequence_detail_nullable_aa_and_nested_experiment():
    s = SequenceInfo.model_validate({
        "id": "33333333-3333-3333-3333-333333333333", "length": 120,
        "is_control": False, "created_at": "2026-07-01T10:00:00Z",
        "experiment": {"experiment_id": "11111111-1111-1111-1111-111111111111",
                       "experiment_code": "EXP-1001"}})
    assert s.aa_string is None and s.experiment.experiment_code == "EXP-1001"
```
- [ ] **Step 2: Run** → FAIL (`ModuleNotFoundError: adaptyv.models`).
- [ ] **Step 3: `adaptyv/models.py`:**
```python
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Generic, Literal, TypeVar, Union

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class _R(BaseModel):
    """Base for response models: tolerate unknown/added fields."""
    model_config = ConfigDict(extra="ignore")


class _Req(BaseModel):
    """Base for request models: strict."""
    model_config = ConfigDict(extra="forbid")


class ExperimentStatus(str, Enum):
    DRAFT = "draft"
    WAITING_FOR_CONFIRMATION = "waiting_for_confirmation"
    CANCELED = "canceled"
    WAITING_FOR_MATERIALS = "waiting_for_materials"
    IN_PRODUCTION = "in_production"
    QUOTE_SENT = "quote_sent"
    IN_QUEUE = "in_queue"
    DATA_ANALYSIS = "data_analysis"
    IN_REVIEW = "in_review"
    DONE = "done"


class ResultsStatus(str, Enum):
    NONE = "none"
    PARTIAL = "partial"
    ALL = "all"


class ExperimentType(str, Enum):
    AFFINITY = "affinity"
    SCREENING = "screening"
    THERMOSTABILITY = "thermostability"
    FLUORESCENCE = "fluorescence"
    EXPRESSION = "expression"
    EPITOPE_BINNING = "epitope_binning"
    ENZYME_ACTIVITY = "enzyme_activity"


class Method(str, Enum):
    BLI = "bli"
    SPR = "spr"


class SequenceType(str, Enum):
    SCFV = "ScFv"
    FAB = "FAB"
    SINGLE_CHAIN = "SingleChain"
    IGG = "IgG"


class Page(_R, Generic[T]):
    items: list[T]
    total: int
    count: int
    offset: int


# ---- result cluster ----
class KineticInterval(_R):
    value: float
    ci_low: float | None = None
    ci_high: float | None = None


class AffinityReplicate(_R):
    replicate: int
    binding: str | None = None
    binding_strength: str | None = None
    confidence: str | None = None
    expression: str | None = None
    fit_quality: str | None = None
    kd: float | None = None
    kd_app: KineticInterval | None = None
    koff: float | None = None
    koff_1to1: KineticInterval | None = None
    koff_method: str | None = None
    kon: float | None = None
    kon_1to1: KineticInterval | None = None
    kon_method: str | None = None
    method: str | None = None
    rmse_max_signal_pct: float | None = None


class SequenceEntry(_R):
    aa_string: str
    control: bool | None = None
    metadata: dict[str, Any] | None = None
    name: str | None = None


class TargetReference(_R):
    name: str
    sequence: str | None = None
    supplier_url: str | None = None
    target_catalog_id: str | None = None


class AffinityResult(_R):
    sequence: SequenceEntry
    kd_units: str
    binding_strength: str
    positive_control: bool
    performance: dict[str, Any]
    replicates: list[AffinityReplicate] = Field(default_factory=list)
    binding: str | None = None
    binding_model: list[str] | None = None
    expression: str | None = None
    fit_quality: str | None = None
    method: list[str] | None = None
    place: int | None = None
    target: TargetReference | None = None
    kd_mean: float | None = None
    kd_log_std: float | None = None
    kd_app: KineticInterval | None = None
    kon_mean: float | None = None
    kon_log_std: float | None = None
    kon_1to1: KineticInterval | None = None
    koff_mean: float | None = None
    koff_log_std: float | None = None
    koff_1to1: KineticInterval | None = None
    concentration_value: float | None = None
    concentration_display: str | None = None


class ThermostabilityResult(_R):
    sequence_id: str
    inflection_pts_for_ratio: list[float]
    onset_pts_for_ratio: list[float]
    bli_result_id: str | None = None
    initial_330nm: float | None = None
    sequence: str | None = None
    sequence_name: str | None = None
    tm: float | None = None


class AffinityResultSummary(AffinityResult):
    result_type: Literal["affinity"]


class ThermostabilityResultSummary(ThermostabilityResult):
    result_type: Literal["thermostability"]


ResultSummary = Annotated[
    Union[AffinityResultSummary, ThermostabilityResultSummary],
    Field(discriminator="result_type"),
]


class ResultInfo(_R):
    id: str
    title: str
    experiment_id: str
    result_type: str
    created_at: datetime
    summary: list[ResultSummary]
    metadata: dict[str, Any]
    data_package_url: str | None = None


# ---- experiments ----
class ExperimentSpecInfo(_R):
    experiment_type: ExperimentType
    target: TargetReference | None = None
    # other spec fields (method, replicates, sequences...) tolerated via extra="ignore"


class ExpInfo(_R):
    id: str
    code: str
    status: ExperimentStatus
    results_status: ResultsStatus
    created_at: datetime
    experiment_url: str
    experiment_spec: ExperimentSpecInfo
    name: str | None = None
    costs: dict[str, Any] | None = None
    stripe_quote_id: str | None = None
    stripe_quote_url: str | None = None
    stripe_invoice_url: str | None = None


class ExperimentListItem(_R):
    id: str
    code: str
    status: ExperimentStatus
    results_status: ResultsStatus
    created_at: datetime
    experiment_url: str
    experiment_type: ExperimentType | None = None
    name: str | None = None
    stripe_quote_url: str | None = None
    stripe_invoice_url: str | None = None


# ---- sequences ----
class SequenceExperimentRef(_R):
    experiment_id: str
    experiment_code: str
    experiment_status: str | None = None


class SequenceInfo(_R):
    id: str
    length: int
    is_control: bool
    created_at: datetime
    experiment: SequenceExperimentRef
    aa_string: str | None = None
    name: str | None = None
    metadata: dict[str, Any] | None = None


class SequenceListItem(_R):
    id: str
    length: int
    experiment_id: str
    experiment_code: str
    is_control: bool
    created_at: datetime
    name: str | None = None
    aa_preview: str | None = None


class SequenceAddRequest(_Req):
    experiment_code: str
    sequences: list[SequenceEntry]


class SequenceAddResponse(_R):
    experiment_id: str
    experiment_code: str
    added_count: int
    sequence_ids: list[str]


# ---- targets ----
class TargetInfo(_R):
    id: str
    name: str
    vendor_name: str
    catalog_number: str
    url: str
    uniprot_id: str | None = None
    pricing: dict[str, Any] | None = None
    details: dict[str, Any] | None = None


# ---- create / estimate ----
class ExperimentSpec(_Req):
    experiment_type: ExperimentType
    sequences: list[SequenceEntry] = Field(default_factory=list)
    target_id: str | None = None
    method: Method | None = None
    antigen_concentrations: list[float] | None = None
    parameters: dict[str, Any] | None = None


class CreateExpRequest(_Req):
    name: str
    experiment_spec: ExperimentSpec
    skip_draft: bool | None = None
    auto_accept_quote: bool | None = None
    webhook_url: str | None = None


class CreateExpResponse(_R):
    experiment_id: str
    error: str | None = None
    stripe_invoice_id: str | None = None
    stripe_hosted_invoice_url: str | None = None


class CostEstimateRequest(_Req):
    experiment_spec: ExperimentSpec


class CostEstimateResponse(_R):
    breakdown: Any | None = None
    incomplete: Any | None = None
    warnings: list[str] | None = None


class ErrorResponse(_R):
    error: str
    request_id: str


class WhoAmIResponse(_R):
    user_id: str
    organizations: list[dict[str, Any]]
    capabilities: list[str]
    expires_at: datetime | None = None
```
- [ ] **Step 4: Run** `python3 -m pytest tests/test_models.py -q` → PASS.
- [ ] **Step 5: Commit** `git add adaptyv/models.py tests/test_models.py && git commit -m "feat: schema-faithful pydantic models (enums, discriminated results, pagination)"`.

---

### Task 3: Transport, errors, pagination, MockTransport + fixtures, contract test

**Files:** Create `adaptyv/errors.py`, `adaptyv/transport.py`, `adaptyv/mocks/__init__.py`,
`adaptyv/mocks/fixtures/{experiments_list.json,experiment_detail.json,results_list.json,targets_list.json,sequences_list.json}`;
Test `tests/test_transport.py`, `tests/test_fixtures_contract.py`.

**Interfaces:**
- `adaptyv.errors`: `AdaptyvError`, `AuthError`, `NotFoundError`, `RateLimitError`,
  `ValidationError`, `TransportError`, `error_for_status(status, message, request_id)`.
- `adaptyv.transport.Transport` protocol:
  `request(method, path, *, params=None, json=None) -> Any` (parsed JSON; raises `AdaptyvError`).
- `adaptyv.transport.MockTransport()` — returns pagination envelopes for list paths and bare
  objects for detail paths; raises `NotFoundError` for unknown ids.

- [ ] **Step 1: Failing tests** — `tests/test_transport.py`:
```python
import pytest
from adaptyv.errors import NotFoundError
from adaptyv.transport import MockTransport

def test_list_returns_pagination_envelope():
    env = MockTransport().request("GET", "/api/v1/experiments")
    assert set(env) >= {"items", "total", "count", "offset"}
    assert isinstance(env["items"], list) and env["items"]

def test_detail_returns_bare_object():
    t = MockTransport()
    exp_id = t.request("GET", "/api/v1/experiments")["items"][0]["id"]
    exp = t.request("GET", f"/api/v1/experiments/{exp_id}")
    assert exp["id"] == exp_id and "experiment_spec" in exp

def test_results_for_experiment_filtered():
    t = MockTransport()
    env = t.request("GET", "/api/v1/results")
    assert env["items"] and env["items"][0]["summary"][0]["result_type"] == "affinity"

def test_unknown_detail_raises():
    with pytest.raises(NotFoundError):
        MockTransport().request("GET", "/api/v1/experiments/00000000-0000-0000-0000-0000000000ff")
```
`tests/test_fixtures_contract.py` — validate every fixture against the **pinned OpenAPI schema**:
```python
"""Contract test: fixtures must validate against the authoritative OpenAPI component
schemas (not just our pydantic models), so mock data cannot drift from the real API."""
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

SPEC = json.loads((Path("tests/data/openapi.json")).read_text())
SCHEMAS = SPEC["components"]["schemas"]
FIX = Path("adaptyv/mocks/fixtures")


def _validator(component: str) -> Draft202012Validator:
    # Resolve $ref against the spec's components using a 2020-12 registry.
    from referencing import Registry, Resource
    from referencing.jsonschema import DRAFT202012
    resources = [(f"#/components/schemas/{n}", Resource(contents=s, specification=DRAFT202012))
                 for n, s in SCHEMAS.items()]
    registry = Registry().with_resources(
        [(uri, res) for uri, res in resources])
    return Draft202012Validator({"$ref": f"#/components/schemas/{component}"},
                                registry=registry)


@pytest.mark.parametrize("fixture,component,is_list", [
    ("experiments_list.json", None, True),
    ("experiment_detail.json", "ExpInfo", False),
    ("results_list.json", None, True),
    ("targets_list.json", None, True),
    ("sequences_list.json", None, True),
])
def test_fixture_validates(fixture, component, is_list):
    data = json.loads((FIX / fixture).read_text())
    if is_list:
        assert set(data) >= {"items", "total", "count", "offset"}
    else:
        Draft202012Validator(SCHEMAS[component]).is_valid  # smoke
        _validator(component).validate(data)
```
> Note: list-endpoint item schemas are inline (not `$ref`), so the list test asserts the
> envelope shape and defers per-item validation to the detail fixtures + pydantic round-trip
> in `test_models`. This keeps the contract test authoritative without duplicating inline schemas.

- [ ] **Step 2: Run** → FAIL (`ModuleNotFoundError: adaptyv.transport`).
- [ ] **Step 3: `adaptyv/errors.py`:**
```python
from __future__ import annotations


class AdaptyvError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None,
                 request_id: str | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.request_id = request_id


class AuthError(AdaptyvError): ...
class NotFoundError(AdaptyvError): ...
class RateLimitError(AdaptyvError): ...
class ValidationError(AdaptyvError): ...
class TransportError(AdaptyvError): ...


def error_for_status(status_code: int, message: str, request_id: str | None = None) -> AdaptyvError:
    m = {401: AuthError, 403: AuthError, 404: NotFoundError, 429: RateLimitError,
         400: ValidationError, 422: ValidationError}
    cls = m.get(status_code, TransportError if status_code >= 500 else AdaptyvError)
    return cls(message, status_code=status_code, request_id=request_id)
```
- [ ] **Step 4: `adaptyv/mocks/__init__.py`:**
```python
from __future__ import annotations
import copy, json
from pathlib import Path
from typing import Any

_FIX = Path(__file__).parent / "fixtures"

def load_fixture(name: str) -> Any:
    return copy.deepcopy(json.loads((_FIX / name).read_text()))  # defensive copy
```
- [ ] **Step 5: `adaptyv/transport.py`:**
```python
from __future__ import annotations
import re
from typing import Any, Protocol

from adaptyv.errors import NotFoundError
from adaptyv.mocks import load_fixture


class Transport(Protocol):
    def request(self, method: str, path: str, *, params: dict | None = None,
                json: dict | None = None) -> Any: ...


def _page(items: list[dict], offset: int = 0) -> dict:
    return {"items": items, "total": len(items), "count": len(items), "offset": offset}


class MockTransport:
    """Serves fixture data with the same shapes as the live API. This is demo mode."""

    def __init__(self) -> None:
        self._experiments = load_fixture("experiments_list.json")["items"]
        self._experiment_detail = load_fixture("experiment_detail.json")
        self._results = load_fixture("results_list.json")["items"]
        self._targets = load_fixture("targets_list.json")["items"]
        self._sequences = load_fixture("sequences_list.json")["items"]

    def request(self, method: str, path: str, *, params=None, json=None) -> Any:
        if method == "GET" and path == "/api/v1/experiments":
            return _page(self._experiments)
        if method == "GET" and path == "/api/v1/results":
            return _page(self._results)
        if method == "GET" and path == "/api/v1/targets":
            return _page(self._targets)
        if method == "GET" and path == "/api/v1/sequences":
            return _page(self._sequences)
        m = re.fullmatch(r"/api/v1/experiments/([^/]+)", path)
        if method == "GET" and m:
            return self._detail(self._experiments, m.group(1),
                                full=self._experiment_detail, kind="experiment")
        m = re.fullmatch(r"/api/v1/experiments/([^/]+)/results", path)
        if method == "GET" and m:
            self._detail(self._experiments, m.group(1), kind="experiment")  # 404 if unknown
            return _page([r for r in self._results if r["experiment_id"] == m.group(1)])
        for coll, kind in ((self._targets, "target"), (self._results, "result"),
                           (self._sequences, "sequence")):
            m = re.fullmatch(rf"/api/v1/{kind}s/([^/]+)", path)
            if method == "GET" and m:
                return self._detail(coll, m.group(1), kind=kind)
        raise NotFoundError(f"MockTransport has no route for {method} {path}", status_code=404)

    def _detail(self, items, item_id, *, full=None, kind="item"):
        for it in items:
            if it["id"] == item_id:
                return full if (full and full.get("id") == item_id) else it
        raise NotFoundError(f"{kind} {item_id} not found", status_code=404)
```
- [ ] **Step 6: Fixtures** (envelopes; `experiment_detail.json` matches its list item's `id`).
  `experiments_list.json`:
```json
{"items": [
  {"id": "11111111-1111-1111-1111-111111111111", "code": "EXP-1001", "status": "done",
   "results_status": "all", "created_at": "2026-07-01T10:00:00Z",
   "experiment_url": "https://devs.adaptyvbio.com/e/EXP-1001", "experiment_type": "affinity",
   "name": "Anti-IL6 binder panel"},
  {"id": "22222222-2222-2222-2222-222222222222", "code": "EXP-1002", "status": "in_production",
   "results_status": "none", "created_at": "2026-07-15T09:00:00Z",
   "experiment_url": "https://devs.adaptyvbio.com/e/EXP-1002", "experiment_type": "affinity",
   "name": "PD-L1 affinity screen"}
], "total": 2, "count": 2, "offset": 0}
```
  `experiment_detail.json`:
```json
{"id": "11111111-1111-1111-1111-111111111111", "code": "EXP-1001", "status": "done",
 "results_status": "all", "created_at": "2026-07-01T10:00:00Z",
 "experiment_url": "https://devs.adaptyvbio.com/e/EXP-1001", "name": "Anti-IL6 binder panel",
 "experiment_spec": {"experiment_type": "affinity",
   "target": {"name": "IL-6", "target_catalog_id": "IL6-001"}}}
```
  `results_list.json`:
```json
{"items": [
  {"id": "aaaaaaaa-0000-0000-0000-000000000001", "title": "Affinity results — Anti-IL6 binder panel",
   "experiment_id": "11111111-1111-1111-1111-111111111111", "result_type": "affinity",
   "created_at": "2026-07-20T10:00:00Z", "metadata": {},
   "data_package_url": "https://devs.adaptyvbio.com/data/EXP-1001.zip",
   "summary": [
     {"result_type": "affinity", "sequence": {"aa_string": "MKAA", "name": "binder-1"},
      "kd_units": "M", "binding_strength": "strong", "positive_control": false,
      "performance": {"verdict": "pass"}, "kd_mean": 1.2e-9,
      "replicates": [{"replicate": 1, "kd": 1.1e-9, "expression": "high"},
                     {"replicate": 2, "kd": 1.3e-9, "expression": "high"}]},
     {"result_type": "affinity", "sequence": {"aa_string": "CTRLP", "name": "pos-control"},
      "kd_units": "M", "binding_strength": "strong", "positive_control": true,
      "performance": {"verdict": "pass"}, "kd_mean": 2.0e-9, "replicates": [{"replicate": 1, "kd": 2.0e-9}]}
   ]}
], "total": 1, "count": 1, "offset": 0}
```
  `targets_list.json`:
```json
{"items": [
  {"id": "44444444-0000-0000-0000-000000000001", "name": "IL-6", "vendor_name": "Acme Bio",
   "catalog_number": "IL6-001", "url": "https://devs.adaptyvbio.com/t/IL6-001", "uniprot_id": "P05231"},
  {"id": "44444444-0000-0000-0000-000000000002", "name": "PD-L1", "vendor_name": "Acme Bio",
   "catalog_number": "PDL1-002", "url": "https://devs.adaptyvbio.com/t/PDL1-002", "uniprot_id": "Q9NZQ7"}
], "total": 2, "count": 2, "offset": 0}
```
  `sequences_list.json`:
```json
{"items": [
  {"id": "33333333-0000-0000-0000-000000000001", "length": 120, "experiment_id": "11111111-1111-1111-1111-111111111111",
   "experiment_code": "EXP-1001", "is_control": false, "created_at": "2026-07-01T10:00:00Z",
   "name": "binder-1", "aa_preview": "MKAA..."}
], "total": 1, "count": 1, "offset": 0}
```
- [ ] **Step 7: Run** `python3 -m pytest tests/test_transport.py tests/test_fixtures_contract.py -q` → PASS.
- [ ] **Step 8: Commit** `git add adaptyv/errors.py adaptyv/transport.py adaptyv/mocks tests/test_transport.py tests/test_fixtures_contract.py && git commit -m "feat: transport, errors, pagination-aware MockTransport + OpenAPI-schema contract test"`.

---

### Task 4: AdaptyvClient + experiments resource (paginated reads)

**Files:** Create `adaptyv/resources/__init__.py`, `adaptyv/resources/experiments.py`,
`adaptyv/client.py`; Modify `adaptyv/__init__.py`; Test `tests/test_experiments_resource.py`.

**Interfaces:**
- `AdaptyvClient(api_key=None, *, mock=False, base_url="https://devs.adaptyvbio.com", transport=None)`
  with `_request(method, path, *, params=None, json=None)` and `_paged(path, model, params) -> list[model]`.
- `client.experiments.list(*, limit=None, offset=None, search=None, filter=None, sort=None) -> list[ExperimentListItem]`
- `client.experiments.get(experiment_id: str) -> ExpInfo`  (UUID only)
- `client.experiments.results(experiment_id: str) -> list[ResultInfo]`

- [ ] **Step 1: Failing test** — `tests/test_experiments_resource.py`:
```python
from adaptyv import AdaptyvClient
from adaptyv.models import ExperimentListItem, ExperimentStatus, ExpInfo, ResultInfo

def test_list_returns_list_items():
    exps = AdaptyvClient(mock=True).experiments.list()
    assert all(isinstance(e, ExperimentListItem) for e in exps)
    assert any(e.status is ExperimentStatus.DONE for e in exps)

def test_get_detail_by_uuid():
    exp = AdaptyvClient(mock=True).experiments.get("11111111-1111-1111-1111-111111111111")
    assert isinstance(exp, ExpInfo) and exp.experiment_spec.experiment_type.value == "affinity"

def test_results_are_typed_and_discriminated():
    c = AdaptyvClient(mock=True)
    results = c.experiments.results("11111111-1111-1111-1111-111111111111")
    assert results and isinstance(results[0], ResultInfo)
    assert results[0].summary[0].result_type == "affinity"
```
- [ ] **Step 2: Run** → FAIL (`ImportError: AdaptyvClient`).
- [ ] **Step 3:** `adaptyv/resources/__init__.py`: empty. `adaptyv/resources/experiments.py`:
```python
from __future__ import annotations
from typing import TYPE_CHECKING
from adaptyv.models import ExperimentListItem, ExpInfo, ResultInfo
if TYPE_CHECKING:
    from adaptyv.client import AdaptyvClient


class ExperimentsResource:
    def __init__(self, client: "AdaptyvClient") -> None:
        self._c = client

    def list(self, *, limit=None, offset=None, search=None, filter=None, sort=None):
        params = {k: v for k, v in dict(limit=limit, offset=offset, search=search,
                                        filter=filter, sort=sort).items() if v is not None}
        return self._c._paged("/api/v1/experiments", ExperimentListItem, params)

    def get(self, experiment_id: str) -> ExpInfo:
        return ExpInfo.model_validate(
            self._c._request("GET", f"/api/v1/experiments/{experiment_id}"))

    def results(self, experiment_id: str) -> list[ResultInfo]:
        return self._c._paged(f"/api/v1/experiments/{experiment_id}/results", ResultInfo, {})
```
  `adaptyv/client.py`:
```python
from __future__ import annotations
import os
from typing import Any, Type, TypeVar
from pydantic import BaseModel, TypeAdapter
from adaptyv.transport import MockTransport, Transport

M = TypeVar("M", bound=BaseModel)


class AdaptyvClient:
    def __init__(self, api_key: str | None = None, *, mock: bool = False,
                 base_url: str = "https://devs.adaptyvbio.com",
                 transport: Transport | None = None) -> None:
        self.base_url = base_url
        if transport is not None:
            self._transport = transport
        elif mock:
            self._transport = MockTransport()
        else:
            from adaptyv.live_transport import LiveTransport  # deferred (Task 7)
            self._transport = LiveTransport(base_url=base_url,
                                            api_key=api_key or os.environ.get("ADAPTYV_API_KEY"))
        from adaptyv.resources.experiments import ExperimentsResource
        self.experiments = ExperimentsResource(self)

    def _request(self, method: str, path: str, *, params=None, json=None) -> Any:
        return self._transport.request(method, path, params=params, json=json)

    def _paged(self, path: str, model: Type[M], params: dict) -> list[M]:
        env = self._request("GET", path, params=params)
        adapter = TypeAdapter(model)
        return [adapter.validate_python(i) for i in env["items"]]
```
  `adaptyv/__init__.py`:
```python
from adaptyv._version import __version__
from adaptyv.client import AdaptyvClient
__all__ = ["__version__", "AdaptyvClient"]
```
- [ ] **Step 4: Run** → PASS. **Step 5: Commit** `git commit -am "feat: AdaptyvClient + paginated experiments resource"`.

---

### Task 5: Write methods — experiments.create/submit/cost_estimate

**Files:** Modify `adaptyv/resources/experiments.py`, `adaptyv/transport.py` (mock POST routes);
Test `tests/test_experiment_writes.py`.

**Interfaces:**
- `experiments.create(request: CreateExpRequest) -> CreateExpResponse` → `POST /api/v1/experiments`
- `experiments.submit(experiment_id: str) -> dict` → `POST /api/v1/experiments/{id}/submit`
- `experiments.cost_estimate(request: CostEstimateRequest) -> CostEstimateResponse` → `POST /api/v1/experiments/cost-estimate`

- [ ] **Step 1: Failing test** — `tests/test_experiment_writes.py`:
```python
from adaptyv import AdaptyvClient
from adaptyv.models import (CreateExpRequest, CreateExpResponse, CostEstimateRequest,
                            CostEstimateResponse, ExperimentSpec, SequenceEntry)

def _spec():
    return ExperimentSpec(experiment_type="affinity", target_id="44444444-0000-0000-0000-000000000001",
                          sequences=[SequenceEntry(aa_string="MKAA", name="binder-1")])

def test_create_returns_experiment_id():
    r = AdaptyvClient(mock=True).experiments.create(
        CreateExpRequest(name="My run", experiment_spec=_spec()))
    assert isinstance(r, CreateExpResponse) and r.experiment_id

def test_cost_estimate_returns_response():
    r = AdaptyvClient(mock=True).experiments.cost_estimate(CostEstimateRequest(experiment_spec=_spec()))
    assert isinstance(r, CostEstimateResponse)
```
- [ ] **Step 2: Run** → FAIL (`AttributeError: create`).
- [ ] **Step 3:** add to `ExperimentsResource`:
```python
    def create(self, request):
        from adaptyv.models import CreateExpResponse
        data = self._c._request("POST", "/api/v1/experiments",
                                 json=request.model_dump(exclude_none=True))
        return CreateExpResponse.model_validate(data)

    def submit(self, experiment_id: str) -> dict:
        return self._c._request("POST", f"/api/v1/experiments/{experiment_id}/submit")

    def cost_estimate(self, request):
        from adaptyv.models import CostEstimateResponse
        data = self._c._request("POST", "/api/v1/experiments/cost-estimate",
                                 json=request.model_dump(exclude_none=True))
        return CostEstimateResponse.model_validate(data)
```
  In `MockTransport.request`, add before the final raise:
```python
        if method == "POST" and path == "/api/v1/experiments":
            return {"experiment_id": "99999999-9999-9999-9999-999999999999"}
        m = re.fullmatch(r"/api/v1/experiments/([^/]+)/submit", path)
        if method == "POST" and m:
            return {"experiment_id": m.group(1), "status": "quote_sent"}
        if method == "POST" and path == "/api/v1/experiments/cost-estimate":
            return {"breakdown": {"total_usd": 4200}, "warnings": []}
        if method == "POST" and path == "/api/v1/sequences":
            body = json or {}
            return {"experiment_id": "11111111-1111-1111-1111-111111111111",
                    "experiment_code": body.get("experiment_code", "EXP-1001"),
                    "added_count": len(body.get("sequences", [])),
                    "sequence_ids": ["33333333-0000-0000-0000-0000000000aa"]}
```
- [ ] **Step 4: Run** → PASS. **Step 5: Commit** `git commit -am "feat: experiment write methods (create/submit/cost_estimate) + mock POST routes"`.

---

### Task 6: sequences, targets, results resources

**Files:** Create `adaptyv/resources/{sequences,targets,results}.py`; Modify `adaptyv/client.py`;
Test `tests/test_other_resources.py`.

**Interfaces:**
- `sequences.list(**q) -> list[SequenceListItem]`, `sequences.get(id) -> SequenceInfo`,
  `sequences.add(request: SequenceAddRequest) -> SequenceAddResponse` (`POST /api/v1/sequences`)
- `targets.list(*, search=None, selfservice_only=None, detailed=None, **q) -> list[TargetInfo]`,
  `targets.get(id) -> TargetInfo`
- `results.list(**q) -> list[ResultInfo]`, `results.get(id) -> ResultInfo`

- [ ] **Step 1: Failing test** — `tests/test_other_resources.py`:
```python
from adaptyv import AdaptyvClient
from adaptyv.models import (ResultInfo, SequenceAddRequest, SequenceAddResponse,
                            SequenceEntry, TargetInfo)

def test_targets_search_returns_typed():
    ts = AdaptyvClient(mock=True).targets.list(search="IL")
    assert ts and all(isinstance(t, TargetInfo) for t in ts)

def test_results_list_discriminated():
    rs = AdaptyvClient(mock=True).results.list()
    assert rs and isinstance(rs[0], ResultInfo)
    assert rs[0].summary[0].result_type == "affinity"

def test_sequences_add():
    r = AdaptyvClient(mock=True).sequences.add(SequenceAddRequest(
        experiment_code="EXP-1001", sequences=[SequenceEntry(aa_string="MKAA")]))
    assert isinstance(r, SequenceAddResponse) and r.added_count == 1
```
- [ ] **Step 2: Run** → FAIL. **Step 3:** write the three resource files (same `_paged`/`_request`
  pattern as Task 4), e.g. `adaptyv/resources/targets.py`:
```python
from __future__ import annotations
from typing import TYPE_CHECKING
from adaptyv.models import TargetInfo
if TYPE_CHECKING:
    from adaptyv.client import AdaptyvClient

class TargetsResource:
    def __init__(self, client): self._c = client
    def list(self, *, search=None, selfservice_only=None, detailed=None, limit=None, offset=None):
        params = {k: v for k, v in dict(search=search, selfservice_only=selfservice_only,
                  detailed=detailed, limit=limit, offset=offset).items() if v is not None}
        return self._c._paged("/api/v1/targets", TargetInfo, params)
    def get(self, target_id: str) -> TargetInfo:
        return TargetInfo.model_validate(self._c._request("GET", f"/api/v1/targets/{target_id}"))
```
  `adaptyv/resources/results.py` (list/get → `ResultInfo`) and `adaptyv/resources/sequences.py`
  (`list` → `SequenceListItem`, `get` → `SequenceInfo`, `add` → POST returning `SequenceAddResponse`)
  follow the identical pattern. Wire in `client.py` after `self.experiments = ...`:
```python
        from adaptyv.resources.sequences import SequencesResource
        from adaptyv.resources.targets import TargetsResource
        from adaptyv.resources.results import ResultsResource
        self.sequences = SequencesResource(self)
        self.targets = TargetsResource(self)
        self.results = ResultsResource(self)
```
  Add a `/api/v1/sequences/{id}` mock detail route + a `sequence_detail.json` fixture (nested
  `experiment`, nullable `aa_string`) so `sequences.get` works.
- [ ] **Step 4: Run** `python3 -m pytest -q` → PASS. **Step 5: Commit** `git commit -am "feat: sequences, targets, results resources"`.

---

### Task 7: LiveTransport (envelope-aware, Retry-After, idempotent-only retry)

**Files:** Create `adaptyv/live_transport.py`; Test `tests/test_live_transport.py`.

**Interfaces:** `LiveTransport(base_url, api_key, *, max_retries=2, sleep=time.sleep)` implementing
`Transport`; retries **only idempotent** methods (GET/HEAD) on 429/5xx, honoring `Retry-After`;
maps errors to typed exceptions using the real `{error, request_id}` body; raises `AuthError`
if no key on a non-health call. `sleep` is injectable for tests.

- [ ] **Step 1: Failing test** — `tests/test_live_transport.py`:
```python
import httpx, pytest, respx
from adaptyv.errors import AuthError, NotFoundError, ValidationError
from adaptyv.live_transport import LiveTransport
BASE = "https://devs.adaptyvbio.com"

def _lt(**kw): return LiveTransport(base_url=BASE, api_key="secret", sleep=lambda *_: None, **kw)

@respx.mock
def test_get_sends_bearer_and_parses_envelope():
    r = respx.get(f"{BASE}/api/v1/experiments").mock(
        return_value=httpx.Response(200, json={"items": [], "total": 0, "count": 0, "offset": 0}))
    assert _lt().request("GET", "/api/v1/experiments")["total"] == 0
    assert r.calls.last.request.headers["authorization"] == "Bearer secret"

@respx.mock
def test_error_body_uses_error_field_and_maps_type():
    respx.get(f"{BASE}/api/v1/x").mock(return_value=httpx.Response(
        404, json={"error": "experiment not found",
                   "request_id": "55555555-5555-5555-5555-555555555555"}))
    with pytest.raises(NotFoundError) as ei:
        _lt().request("GET", "/api/v1/x")
    assert "experiment not found" in str(ei.value)

@respx.mock
def test_retries_get_on_429_then_succeeds_exactly_twice():
    route = respx.get(f"{BASE}/api/v1/results").mock(side_effect=[
        httpx.Response(429, headers={"Retry-After": "0"}, json={"error": "slow", "request_id": "x"}),
        httpx.Response(200, json={"items": [], "total": 0, "count": 0, "offset": 0})])
    _lt(max_retries=2).request("GET", "/api/v1/results")
    assert route.call_count == 2

@respx.mock
def test_post_is_not_retried():
    route = respx.post(f"{BASE}/api/v1/experiments").mock(
        return_value=httpx.Response(503, json={"error": "down", "request_id": "x"}))
    with pytest.raises(Exception):
        _lt(max_retries=2).request("POST", "/api/v1/experiments", json={})
    assert route.call_count == 1

def test_missing_key_raises_auth():
    with pytest.raises(AuthError):
        LiveTransport(base_url=BASE, api_key=None).request("GET", "/api/v1/experiments")
```
- [ ] **Step 2: Run** → FAIL. **Step 3: `adaptyv/live_transport.py`:**
```python
from __future__ import annotations
import time
from typing import Any, Callable
import httpx
from adaptyv.errors import AuthError, TransportError, error_for_status

_RETRY = {429, 500, 502, 503, 504}
_IDEMPOTENT = {"GET", "HEAD"}


class LiveTransport:
    def __init__(self, base_url: str, api_key: str | None, *, max_retries: int = 2,
                 timeout: float = 30.0, sleep: Callable[[float], None] = time.sleep) -> None:
        self._base = base_url.rstrip("/")
        self._key = api_key
        self._max = max_retries
        self._sleep = sleep
        self._http = httpx.Client(timeout=timeout)

    def request(self, method: str, path: str, *, params=None, json=None) -> Any:
        if not self._key and not path.startswith("/api/v1/info/health"):
            raise AuthError("No API key. Pass api_key=, set ADAPTYV_API_KEY, or use mock=True.",
                            status_code=401)
        url = f"{self._base}{path}"
        headers = {"Authorization": f"Bearer {self._key}"} if self._key else {}
        attempts = self._max + 1 if method.upper() in _IDEMPOTENT else 1
        for i in range(attempts):
            resp = self._http.request(method, url, params=params, json=json, headers=headers)
            if resp.status_code in _RETRY and i < attempts - 1:
                self._sleep(float(resp.headers.get("Retry-After", 0.2 * (i + 1))))
                continue
            if resp.status_code >= 400:
                raise _to_error(resp)
            return resp.json() if resp.content else None
        raise TransportError("request failed after retries")


def _to_error(resp: httpx.Response):
    msg, rid = f"HTTP {resp.status_code}", resp.headers.get("x-request-id")
    try:
        body = resp.json()
        msg = body.get("error", msg)
        rid = body.get("request_id", rid)
    except Exception:
        pass
    return error_for_status(resp.status_code, msg, rid)
```
- [ ] **Step 4: Run** → PASS. **Step 5: Commit** `git commit -am "feat: LiveTransport (idempotent-only retry, Retry-After, real error body)"`.

---

### Task 8: Minimal Typer CLI

**Files:** Create `adaptyv/cli.py`; Test `tests/test_cli.py`.

**Interfaces:** `adaptyv.cli.app` with `experiments list [--mock/--no-mock]` and
`results get <uuid> [--mock/--no-mock]`; `--mock` defaults True.

- [ ] **Step 1: Failing test** — `tests/test_cli.py`:
```python
from typer.testing import CliRunner
from adaptyv.cli import app
runner = CliRunner()

def test_experiments_list():
    r = runner.invoke(app, ["experiments", "list"])
    assert r.exit_code == 0 and "EXP-1001" in r.stdout and "done" in r.stdout

def test_results_get_renders_affinity():
    r = runner.invoke(app, ["results", "get", "aaaaaaaa-0000-0000-0000-000000000001"])
    assert r.exit_code == 0 and "kd_mean" in r.stdout and "1.2e-09" in r.stdout
```
- [ ] **Step 2: Run** → FAIL. **Step 3: `adaptyv/cli.py`:**
```python
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
```
- [ ] **Step 4: Run** `python3 -m pytest -q` (full suite) → PASS. **Step 5: Commit** `git commit -am "feat: minimal Typer CLI"`.

---

## Phase 1 Definition of Done

- `python3 -m pip install -e ".[dev]"` succeeds; `python3 -m pytest -q` fully green.
- `python3 -c "from adaptyv import AdaptyvClient as C; print(C(mock=True).experiments.list()[0].code)"` → `EXP-1001`.
- `adaptyv experiments list` prints mock experiments with no key.
- Contract test validates fixtures against the **pinned OpenAPI schema** (sha256 recorded above).
- Mock and live transports return identical shapes (pagination envelopes for lists).

**Next (written just-in-time):** Phase 2 — governance (approval state machine + audit;
hash-chaining is a labeled *stretch*), then Phase 3 — ExperimentWatcher (anomaly policy
+ fact-injected drafting) with anomalous affinity fixtures.
```
