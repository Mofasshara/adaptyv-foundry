# Phase 1 — Adaptyv Python SDK Core — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the typed, sync Python SDK core (`adaptyv`) — models, pluggable transport with mock mode, client + resource namespaces, live HTTP transport, and a minimal CLI — so that `AdaptyvClient(mock=True)` returns typed lab data with no API key.

**Architecture:** Hand-written `httpx` + `pydantic v2` client. A `Transport` protocol decouples the client from I/O, with `MockTransport` (JSON fixtures, no key) and `LiveTransport` (real API). Resources are thin namespaces on the client. This SDK is the single source of truth the later MCP server, agent, and evals all reuse.

**Tech Stack:** Python 3.11+, pydantic v2, httpx, Typer (CLI), pytest, respx (httpx mocking).

## Global Constraints

- Python **3.11+** (`requires-python = ">=3.11"`).
- Import package name is **`adaptyv`**; distribution name is **`adaptyv-foundry-sdk`** (TestPyPI). Do NOT publish to real PyPI.
- Sync only — no `async`/`await` anywhere in the SDK.
- pydantic **v2** API (`model_validate`, `model_dump`, `Field`, `field_validator`).
- API base URL default: `https://devs.adaptyvbio.com`; all paths prefixed `/api/v1`.
- Never log or print API keys. Keys come from the `api_key` arg or `ADAPTYV_API_KEY` env var only.
- Every task ends green (`pytest -q` passes) and is committed.
- Follow TDD: failing test first, minimal code, green, commit.

---

### Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `adaptyv/__init__.py`
- Create: `adaptyv/_version.py`
- Create: `tests/__init__.py`
- Create: `tests/test_smoke.py`

**Interfaces:**
- Consumes: nothing.
- Produces: importable `adaptyv` package exposing `adaptyv.__version__: str`.

- [ ] **Step 1: Write the failing test**

`tests/test_smoke.py`:
```python
import adaptyv


def test_package_exposes_version():
    assert isinstance(adaptyv.__version__, str)
    assert adaptyv.__version__
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_smoke.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'adaptyv'`.

- [ ] **Step 3: Write pyproject.toml**

`pyproject.toml`:
```toml
[project]
name = "adaptyv-foundry-sdk"
version = "0.1.0"
description = "Typed Python SDK for the Adaptyv Foundry lab API (unofficial)."
requires-python = ">=3.11"
readme = "README.md"
dependencies = [
    "httpx>=0.27",
    "pydantic>=2.7",
    "typer>=0.12",
]

[project.optional-dependencies]
dev = ["pytest>=8", "respx>=0.21", "fastapi>=0.110", "anthropic>=0.40"]

[project.scripts]
adaptyv = "adaptyv.cli:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["adaptyv"]

[tool.pytest.ini_options]
addopts = "-q"
markers = ["live_llm: tests that call a real LLM (need ANTHROPIC_API_KEY)"]
```

- [ ] **Step 4: Create package files**

`adaptyv/_version.py`:
```python
__version__ = "0.1.0"
```

`adaptyv/__init__.py`:
```python
from adaptyv._version import __version__

__all__ = ["__version__"]
```

`tests/__init__.py`: (empty file)

Create `README.md` with a single line so `readme` resolves:
```markdown
# adaptyv-foundry-sdk
Unofficial typed Python SDK for the Adaptyv Foundry lab API. See docs/.
```

- [ ] **Step 5: Install editable + run test**

Run: `pip install -e ".[dev]" && python -m pytest tests/test_smoke.py -q`
Expected: PASS (1 passed).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml adaptyv/ tests/ README.md
git commit -m "feat: scaffold adaptyv SDK package"
```

---

### Task 2: Enums and pydantic models

**Files:**
- Create: `adaptyv/models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Consumes: nothing.
- Produces (all importable from `adaptyv.models`):
  - Enums: `ExperimentStatus`, `ResultsStatus`, `ExperimentType` (str enums).
  - Models: `KineticInterval`, `AffinityReplicate`, `AffinityResult`, `ResultSummary`,
    `ResultInfo`, `ExpInfo`, `SequenceInfo`, `SequenceListItem`, `SequenceAddRequest`,
    `TargetInfo`, `ErrorResponse`, `WhoAmIResponse`.
- Field definitions mirror the Foundry OpenAPI spec
  (`https://foundry-api-public.adaptyvbio.com/api/v1/openapi.json`).

- [ ] **Step 1: Write the failing test**

`tests/test_models.py`:
```python
from adaptyv.models import (
    AffinityResult,
    ExperimentStatus,
    ExpInfo,
    KineticInterval,
    ResultInfo,
)


def test_experiment_status_enum_values():
    assert ExperimentStatus.COMPLETE.value == "complete"
    assert ExperimentStatus("draft") is ExperimentStatus.DRAFT
    assert {s.value for s in ExperimentStatus} >= {
        "draft", "complete", "cancelled", "rejected", "in_production",
        "in_analysis", "waiting_for_confirmation", "waiting_for_materials",
    }


def test_kinetic_interval_parses():
    ki = KineticInterval.model_validate({"value": 1.2e-9, "lower": 1.0e-9, "upper": 1.5e-9})
    assert ki.value == 1.2e-9 and ki.lower < ki.upper


def test_affinity_result_optional_kinetics_default_none():
    ar = AffinityResult.model_validate({
        "sequence": "MK...",
        "kd_units": "M",
        "binding_strength": "strong",
        "positive_control": False,
        "performance": "pass",
        "replicates": [],
    })
    assert ar.kd_mean is None
    assert ar.positive_control is False
    assert ar.replicates == []


def test_expinfo_requires_core_fields():
    exp = ExpInfo.model_validate({
        "id": "11111111-1111-1111-1111-111111111111",
        "code": "EXP-001",
        "status": "complete",
        "results_status": "all",
        "created_at": "2026-07-01T10:00:00Z",
        "experiment_url": "https://devs.adaptyvbio.com/experiments/EXP-001",
    })
    assert exp.status is ExperimentStatus.COMPLETE
    assert exp.name is None


def test_resultinfo_nested_summary():
    ri = ResultInfo.model_validate({
        "id": "22222222-2222-2222-2222-222222222222",
        "title": "Affinity results",
        "experiment_id": "11111111-1111-1111-1111-111111111111",
        "result_type": "affinity",
        "created_at": "2026-07-20T10:00:00Z",
        "summary": [{
            "sequence": "MK...",
            "sequence_id": "33333333-3333-3333-3333-333333333333",
            "readout": "kd",
            "value": "1.2e-9",
            "value_units": "M",
        }],
        "metadata": {},
    })
    assert ri.summary[0].readout == "kd"
    assert ri.data_package_url is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_models.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'adaptyv.models'`.

- [ ] **Step 3: Write the models**

`adaptyv/models.py`:
```python
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    # Tolerate unknown fields from the API without crashing (forward-compat).
    model_config = ConfigDict(extra="ignore")


class ExperimentStatus(str, Enum):
    DRAFT = "draft"
    WAITING_FOR_CONFIRMATION = "waiting_for_confirmation"
    WAITING_FOR_MATERIALS = "waiting_for_materials"
    IN_PRODUCTION = "in_production"
    IN_ANALYSIS = "in_analysis"
    COMPLETE = "complete"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


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


class KineticInterval(_Model):
    value: float
    lower: float
    upper: float


class AffinityReplicate(_Model):
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


class AffinityResult(_Model):
    sequence: str
    kd_units: str
    binding_strength: str
    positive_control: bool
    performance: str
    replicates: list[AffinityReplicate] = Field(default_factory=list)
    binding: str | None = None
    binding_model: list[str] | None = None
    expression: str | None = None
    fit_quality: str | None = None
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


class ResultSummary(_Model):
    sequence: str
    sequence_id: str
    readout: str
    value: str | float | None
    value_units: str | None
    value_range: dict[str, Any] | None = None
    confidence: str | None = None


class ResultInfo(_Model):
    id: str
    title: str
    experiment_id: str
    result_type: str
    created_at: datetime
    summary: list[ResultSummary]
    metadata: dict[str, Any]
    data_package_url: str | None = None


class ExpInfo(_Model):
    id: str
    code: str
    status: ExperimentStatus
    results_status: ResultsStatus
    created_at: datetime
    experiment_url: str
    name: str | None = None
    experiment_type: ExperimentType | None = None
    stripe_quote_url: str | None = None
    stripe_invoice_url: str | None = None
    target: dict[str, Any] | None = None
    sequences: list[Any] | None = None
    parameters: dict[str, Any] | None = None
    webhook_url: str | None = None


class SequenceInfo(_Model):
    id: str
    aa_string: str
    length: int
    experiment_id: str
    experiment_code: str
    is_control: bool
    created_at: datetime
    name: str | None = None
    metadata: dict[str, Any] | None = None


class SequenceListItem(_Model):
    id: str
    length: int
    experiment_id: str
    experiment_code: str
    is_control: bool
    created_at: datetime
    name: str | None = None
    aa_preview: str | None = None


class SequenceAddRequest(_Model):
    experiment_code: str
    sequences: dict[str, str]


class TargetInfo(_Model):
    id: str
    name: str
    vendor_name: str
    catalog_number: str
    url: str
    uniprot_id: str | None = None
    pricing: dict[str, Any] | None = None
    details: dict[str, Any] | None = None


class ErrorResponse(_Model):
    error: str
    message: str
    status_code: int
    request_id: str


class WhoAmIResponse(_Model):
    user_id: str
    organizations: list[dict[str, Any]]
    capabilities: list[str]
    expires_at: datetime | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_models.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add adaptyv/models.py tests/test_models.py
git commit -m "feat: add pydantic models mirroring Foundry OpenAPI schemas"
```

---

### Task 3: Transport protocol, errors, MockTransport + fixtures, contract test

**Files:**
- Create: `adaptyv/errors.py`
- Create: `adaptyv/transport.py`
- Create: `adaptyv/mocks/__init__.py`
- Create: `adaptyv/mocks/fixtures/experiments.json`
- Create: `adaptyv/mocks/fixtures/results.json`
- Test: `tests/test_transport.py`
- Test: `tests/test_fixtures_contract.py`

**Interfaces:**
- Consumes: `adaptyv.models` (Task 2).
- Produces:
  - `adaptyv.errors`: `AdaptyvError`, `AuthError`, `NotFoundError`, `RateLimitError`,
    `ValidationError`, `TransportError` (all subclasses of `AdaptyvError`).
  - `adaptyv.transport.Transport` protocol with
    `request(method: str, path: str, *, params: dict | None = None, json: dict | None = None) -> Any`
    (returns already-parsed JSON, raises `AdaptyvError` subclasses on HTTP errors).
  - `adaptyv.transport.MockTransport(fixtures_dir: str | None = None)` implementing `Transport`
    by routing `(method, path)` to fixture data.

- [ ] **Step 1: Write the failing tests**

`tests/test_transport.py`:
```python
import pytest

from adaptyv.errors import NotFoundError
from adaptyv.transport import MockTransport


def test_mock_lists_experiments():
    t = MockTransport()
    data = t.request("GET", "/api/v1/experiments")
    assert isinstance(data, list) and len(data) >= 1
    assert all("code" in e for e in data)


def test_mock_gets_experiment_results():
    t = MockTransport()
    exps = t.request("GET", "/api/v1/experiments")
    complete = next(e for e in exps if e["status"] == "complete")
    results = t.request("GET", f"/api/v1/experiments/{complete['id']}/results")
    assert isinstance(results, list) and results


def test_mock_unknown_path_raises_not_found():
    t = MockTransport()
    with pytest.raises(NotFoundError):
        t.request("GET", "/api/v1/experiments/does-not-exist/results")
```

`tests/test_fixtures_contract.py`:
```python
"""Contract test: every fixture must validate against the real pydantic models.
This is what stops mock data from silently drifting from the API schema."""
from adaptyv.mocks import load_fixture
from adaptyv.models import ExpInfo, ResultInfo


def test_experiment_fixtures_validate():
    for raw in load_fixture("experiments.json"):
        ExpInfo.model_validate(raw)


def test_result_fixtures_validate():
    for raw in load_fixture("results.json"):
        ResultInfo.model_validate(raw)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_transport.py tests/test_fixtures_contract.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'adaptyv.transport'`.

- [ ] **Step 3: Write errors**

`adaptyv/errors.py`:
```python
from __future__ import annotations


class AdaptyvError(Exception):
    """Base class for all SDK errors."""

    def __init__(self, message: str, *, status_code: int | None = None,
                 request_id: str | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.request_id = request_id


class AuthError(AdaptyvError):
    """401/403 — missing or insufficient credentials."""


class NotFoundError(AdaptyvError):
    """404 — resource does not exist."""


class RateLimitError(AdaptyvError):
    """429 — too many requests."""


class ValidationError(AdaptyvError):
    """400/422 — request rejected by the API."""


class TransportError(AdaptyvError):
    """Network/5xx or otherwise unexpected transport failure."""


def error_for_status(status_code: int, message: str, request_id: str | None = None) -> AdaptyvError:
    mapping = {401: AuthError, 403: AuthError, 404: NotFoundError,
               429: RateLimitError, 400: ValidationError, 422: ValidationError}
    cls = mapping.get(status_code, TransportError if status_code >= 500 else AdaptyvError)
    return cls(message, status_code=status_code, request_id=request_id)
```

- [ ] **Step 4: Write the fixture loader + MockTransport**

`adaptyv/mocks/__init__.py`:
```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> Any:
    return json.loads((_FIXTURES / name).read_text())
```

`adaptyv/transport.py`:
```python
from __future__ import annotations

import re
from typing import Any, Protocol

from adaptyv.errors import NotFoundError
from adaptyv.mocks import load_fixture


class Transport(Protocol):
    def request(self, method: str, path: str, *, params: dict | None = None,
                json: dict | None = None) -> Any: ...


class MockTransport:
    """Serves fixture data with no network or API key. This is demo mode."""

    def __init__(self, fixtures_dir: str | None = None) -> None:
        self._experiments: list[dict] = load_fixture("experiments.json")
        self._results: list[dict] = load_fixture("results.json")

    def request(self, method: str, path: str, *, params: dict | None = None,
                json: dict | None = None) -> Any:
        if method == "GET" and path == "/api/v1/experiments":
            return self._experiments
        m = re.fullmatch(r"/api/v1/experiments/([^/]+)", path)
        if method == "GET" and m:
            return self._get_experiment(m.group(1))
        m = re.fullmatch(r"/api/v1/experiments/([^/]+)/results", path)
        if method == "GET" and m:
            return self._results_for(m.group(1))
        raise NotFoundError(f"MockTransport has no route for {method} {path}",
                            status_code=404)

    def _get_experiment(self, exp_id: str) -> dict:
        for e in self._experiments:
            if e["id"] == exp_id or e["code"] == exp_id:
                return e
        raise NotFoundError(f"experiment {exp_id} not found", status_code=404)

    def _results_for(self, exp_id: str) -> list[dict]:
        exp = self._get_experiment(exp_id)  # raises NotFoundError if unknown
        return [r for r in self._results if r["experiment_id"] == exp["id"]]
```

- [ ] **Step 5: Write the fixtures**

`adaptyv/mocks/fixtures/experiments.json` (healthy complete + a running draft; extend in Phase 3 with anomalous ones):
```json
[
  {
    "id": "11111111-1111-1111-1111-111111111111",
    "code": "EXP-1001",
    "status": "complete",
    "results_status": "all",
    "created_at": "2026-07-01T10:00:00Z",
    "experiment_url": "https://devs.adaptyvbio.com/experiments/EXP-1001",
    "name": "Anti-IL6 binder panel",
    "experiment_type": "affinity"
  },
  {
    "id": "22222222-2222-2222-2222-222222222222",
    "code": "EXP-1002",
    "status": "in_production",
    "results_status": "none",
    "created_at": "2026-07-15T09:00:00Z",
    "experiment_url": "https://devs.adaptyvbio.com/experiments/EXP-1002",
    "name": "PD-L1 affinity screen",
    "experiment_type": "affinity"
  }
]
```

`adaptyv/mocks/fixtures/results.json`:
```json
[
  {
    "id": "aaaaaaaa-0000-0000-0000-000000000001",
    "title": "Affinity results — Anti-IL6 binder panel",
    "experiment_id": "11111111-1111-1111-1111-111111111111",
    "result_type": "affinity",
    "created_at": "2026-07-20T10:00:00Z",
    "metadata": {},
    "data_package_url": "https://devs.adaptyvbio.com/data/EXP-1001.zip",
    "summary": [
      {"sequence": "MKAA...", "sequence_id": "33333333-0000-0000-0000-000000000001",
       "readout": "kd", "value": 1.2e-9, "value_units": "M", "confidence": "high"},
      {"sequence": "MKBB...", "sequence_id": "33333333-0000-0000-0000-000000000002",
       "readout": "kd", "value": 4.5e-8, "value_units": "M", "confidence": "medium"},
      {"sequence": "CTRLPOS...", "sequence_id": "33333333-0000-0000-0000-0000000000ff",
       "readout": "kd", "value": 2.0e-9, "value_units": "M", "confidence": "high"}
    ]
  }
]
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_transport.py tests/test_fixtures_contract.py -q`
Expected: PASS (5 passed).

- [ ] **Step 7: Commit**

```bash
git add adaptyv/errors.py adaptyv/transport.py adaptyv/mocks/ tests/test_transport.py tests/test_fixtures_contract.py
git commit -m "feat: add transport protocol, errors, MockTransport + fixtures with contract test"
```

---

### Task 4: AdaptyvClient + experiments resource

**Files:**
- Create: `adaptyv/resources/__init__.py`
- Create: `adaptyv/resources/experiments.py`
- Create: `adaptyv/client.py`
- Modify: `adaptyv/__init__.py` (export `AdaptyvClient`)
- Test: `tests/test_experiments_resource.py`

**Interfaces:**
- Consumes: `Transport`/`MockTransport` (Task 3), models (Task 2).
- Produces:
  - `adaptyv.client.AdaptyvClient(api_key: str | None = None, mock: bool = False, base_url: str = "https://devs.adaptyvbio.com", transport: Transport | None = None)`.
  - `client.experiments` → `ExperimentsResource` with:
    - `list() -> list[ExpInfo]`
    - `get(experiment_id: str) -> ExpInfo`
    - `results(experiment_id: str) -> list[ResultInfo]`
  - `AdaptyvClient` exported from `adaptyv`.

- [ ] **Step 1: Write the failing test**

`tests/test_experiments_resource.py`:
```python
from adaptyv import AdaptyvClient
from adaptyv.models import ExpInfo, ExperimentStatus, ResultInfo


def test_list_experiments_returns_typed_models():
    client = AdaptyvClient(mock=True)
    exps = client.experiments.list()
    assert all(isinstance(e, ExpInfo) for e in exps)
    assert any(e.status is ExperimentStatus.COMPLETE for e in exps)


def test_get_experiment_by_code():
    client = AdaptyvClient(mock=True)
    exp = client.experiments.get("EXP-1001")
    assert exp.code == "EXP-1001"


def test_experiment_results_typed():
    client = AdaptyvClient(mock=True)
    exp = client.experiments.get("EXP-1001")
    results = client.experiments.results(exp.id)
    assert results and all(isinstance(r, ResultInfo) for r in results)
    assert results[0].summary[0].readout == "kd"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_experiments_resource.py -q`
Expected: FAIL — `ImportError: cannot import name 'AdaptyvClient'`.

- [ ] **Step 3: Write the resource + client**

`adaptyv/resources/__init__.py`: (empty file)

`adaptyv/resources/experiments.py`:
```python
from __future__ import annotations

from typing import TYPE_CHECKING

from adaptyv.models import ExpInfo, ResultInfo

if TYPE_CHECKING:
    from adaptyv.client import AdaptyvClient


class ExperimentsResource:
    def __init__(self, client: "AdaptyvClient") -> None:
        self._client = client

    def list(self) -> list[ExpInfo]:
        data = self._client._request("GET", "/api/v1/experiments")
        return [ExpInfo.model_validate(d) for d in data]

    def get(self, experiment_id: str) -> ExpInfo:
        data = self._client._request("GET", f"/api/v1/experiments/{experiment_id}")
        return ExpInfo.model_validate(data)

    def results(self, experiment_id: str) -> list[ResultInfo]:
        data = self._client._request("GET", f"/api/v1/experiments/{experiment_id}/results")
        return [ResultInfo.model_validate(d) for d in data]
```

`adaptyv/client.py`:
```python
from __future__ import annotations

import os
from typing import Any

from adaptyv.resources.experiments import ExperimentsResource
from adaptyv.transport import MockTransport, Transport


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
            from adaptyv.live_transport import LiveTransport  # deferred (Task 6)
            key = api_key or os.environ.get("ADAPTYV_API_KEY")
            self._transport = LiveTransport(base_url=base_url, api_key=key)
        self.experiments = ExperimentsResource(self)

    def _request(self, method: str, path: str, *, params: dict | None = None,
                 json: dict | None = None) -> Any:
        return self._transport.request(method, path, params=params, json=json)
```

`adaptyv/__init__.py`:
```python
from adaptyv._version import __version__
from adaptyv.client import AdaptyvClient

__all__ = ["__version__", "AdaptyvClient"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_experiments_resource.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add adaptyv/resources/ adaptyv/client.py adaptyv/__init__.py tests/test_experiments_resource.py
git commit -m "feat: add AdaptyvClient and experiments resource"
```

---

### Task 5: sequences, targets, results resources

**Files:**
- Create: `adaptyv/resources/sequences.py`
- Create: `adaptyv/resources/targets.py`
- Create: `adaptyv/resources/results.py`
- Create: `adaptyv/mocks/fixtures/targets.json`
- Modify: `adaptyv/client.py` (wire the three resources)
- Modify: `adaptyv/transport.py` (routes for `/sequences`, `/targets`, `/results`)
- Test: `tests/test_other_resources.py`

**Interfaces:**
- Consumes: client + transport + models.
- Produces:
  - `client.sequences.list() -> list[SequenceListItem]`, `client.sequences.get(id) -> SequenceInfo`
  - `client.targets.list() -> list[TargetInfo]`, `client.targets.get(id) -> TargetInfo`
  - `client.results.list() -> list[ResultInfo]`, `client.results.get(id) -> ResultInfo`
  - MockTransport routes: `GET /api/v1/targets`, `GET /api/v1/targets/{id}`,
    `GET /api/v1/results`, `GET /api/v1/results/{id}`, `GET /api/v1/sequences`.

- [ ] **Step 1: Write the failing test**

`tests/test_other_resources.py`:
```python
from adaptyv import AdaptyvClient
from adaptyv.models import ResultInfo, TargetInfo


def test_targets_list_and_get():
    c = AdaptyvClient(mock=True)
    targets = c.targets.list()
    assert targets and all(isinstance(t, TargetInfo) for t in targets)
    one = c.targets.get(targets[0].id)
    assert one.id == targets[0].id


def test_results_list_and_get():
    c = AdaptyvClient(mock=True)
    results = c.results.list()
    assert results and all(isinstance(r, ResultInfo) for r in results)
    one = c.results.get(results[0].id)
    assert one.id == results[0].id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_other_resources.py -q`
Expected: FAIL — `AttributeError: 'AdaptyvClient' object has no attribute 'targets'`.

- [ ] **Step 3: Add the targets fixture**

`adaptyv/mocks/fixtures/targets.json`:
```json
[
  {"id": "44444444-0000-0000-0000-000000000001", "name": "IL-6",
   "vendor_name": "Acme Bio", "catalog_number": "IL6-001",
   "url": "https://devs.adaptyvbio.com/targets/IL6-001", "uniprot_id": "P05231"},
  {"id": "44444444-0000-0000-0000-000000000002", "name": "PD-L1",
   "vendor_name": "Acme Bio", "catalog_number": "PDL1-002",
   "url": "https://devs.adaptyvbio.com/targets/PDL1-002", "uniprot_id": "Q9NZQ7"}
]
```

- [ ] **Step 4: Extend MockTransport routes**

In `adaptyv/transport.py`, load targets in `__init__`:
```python
        self._targets: list[dict] = load_fixture("targets.json")
```
and add these branches to `request` (before the final `raise`):
```python
        if method == "GET" and path == "/api/v1/targets":
            return self._targets
        m = re.fullmatch(r"/api/v1/targets/([^/]+)", path)
        if method == "GET" and m:
            return self._one(self._targets, m.group(1), "target")
        if method == "GET" and path == "/api/v1/results":
            return self._results
        m = re.fullmatch(r"/api/v1/results/([^/]+)", path)
        if method == "GET" and m:
            return self._one(self._results, m.group(1), "result")
        if method == "GET" and path == "/api/v1/sequences":
            return []
```
and add a helper method:
```python
    def _one(self, items: list[dict], item_id: str, kind: str) -> dict:
        for it in items:
            if it["id"] == item_id:
                return it
        raise NotFoundError(f"{kind} {item_id} not found", status_code=404)
```

- [ ] **Step 5: Write the three resources**

`adaptyv/resources/targets.py`:
```python
from __future__ import annotations

from typing import TYPE_CHECKING

from adaptyv.models import TargetInfo

if TYPE_CHECKING:
    from adaptyv.client import AdaptyvClient


class TargetsResource:
    def __init__(self, client: "AdaptyvClient") -> None:
        self._client = client

    def list(self) -> list[TargetInfo]:
        data = self._client._request("GET", "/api/v1/targets")
        return [TargetInfo.model_validate(d) for d in data]

    def get(self, target_id: str) -> TargetInfo:
        data = self._client._request("GET", f"/api/v1/targets/{target_id}")
        return TargetInfo.model_validate(data)
```

`adaptyv/resources/results.py`:
```python
from __future__ import annotations

from typing import TYPE_CHECKING

from adaptyv.models import ResultInfo

if TYPE_CHECKING:
    from adaptyv.client import AdaptyvClient


class ResultsResource:
    def __init__(self, client: "AdaptyvClient") -> None:
        self._client = client

    def list(self) -> list[ResultInfo]:
        data = self._client._request("GET", "/api/v1/results")
        return [ResultInfo.model_validate(d) for d in data]

    def get(self, result_id: str) -> ResultInfo:
        data = self._client._request("GET", f"/api/v1/results/{result_id}")
        return ResultInfo.model_validate(data)
```

`adaptyv/resources/sequences.py`:
```python
from __future__ import annotations

from typing import TYPE_CHECKING

from adaptyv.models import SequenceInfo, SequenceListItem

if TYPE_CHECKING:
    from adaptyv.client import AdaptyvClient


class SequencesResource:
    def __init__(self, client: "AdaptyvClient") -> None:
        self._client = client

    def list(self) -> list[SequenceListItem]:
        data = self._client._request("GET", "/api/v1/sequences")
        return [SequenceListItem.model_validate(d) for d in data]

    def get(self, sequence_id: str) -> SequenceInfo:
        data = self._client._request("GET", f"/api/v1/sequences/{sequence_id}")
        return SequenceInfo.model_validate(data)
```

- [ ] **Step 6: Wire resources into the client**

In `adaptyv/client.py`, add imports and attributes after `self.experiments = ...`:
```python
from adaptyv.resources.sequences import SequencesResource
from adaptyv.resources.targets import TargetsResource
from adaptyv.resources.results import ResultsResource
```
```python
        self.sequences = SequencesResource(self)
        self.targets = TargetsResource(self)
        self.results = ResultsResource(self)
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `python -m pytest tests/test_other_resources.py tests/test_fixtures_contract.py -q`
Expected: PASS (all green).

- [ ] **Step 8: Commit**

```bash
git add adaptyv/resources/ adaptyv/transport.py adaptyv/client.py adaptyv/mocks/fixtures/targets.json tests/test_other_resources.py
git commit -m "feat: add sequences, targets, results resources"
```

---

### Task 6: LiveTransport (httpx) with retry + error mapping

**Files:**
- Create: `adaptyv/live_transport.py`
- Test: `tests/test_live_transport.py`

**Interfaces:**
- Consumes: `adaptyv.errors` (Task 3).
- Produces: `adaptyv.live_transport.LiveTransport(base_url: str, api_key: str | None, max_retries: int = 2)` implementing the `Transport` protocol; retries on 429/5xx with backoff; maps error responses to typed exceptions; raises `AuthError` if no key on a non-health call.

- [ ] **Step 1: Write the failing test** (uses `respx` to mock httpx)

`tests/test_live_transport.py`:
```python
import httpx
import pytest
import respx

from adaptyv.errors import AuthError, NotFoundError
from adaptyv.live_transport import LiveTransport

BASE = "https://devs.adaptyvbio.com"


@respx.mock
def test_get_success_sends_bearer_and_parses_json():
    route = respx.get(f"{BASE}/api/v1/experiments").mock(
        return_value=httpx.Response(200, json=[{"code": "EXP-1"}]))
    t = LiveTransport(base_url=BASE, api_key="secret")
    data = t.request("GET", "/api/v1/experiments")
    assert data == [{"code": "EXP-1"}]
    assert route.calls.last.request.headers["authorization"] == "Bearer secret"


@respx.mock
def test_404_maps_to_not_found():
    respx.get(f"{BASE}/api/v1/experiments/x").mock(
        return_value=httpx.Response(404, json={
            "error": "not_found", "message": "nope", "status_code": 404,
            "request_id": "55555555-5555-5555-5555-555555555555"}))
    t = LiveTransport(base_url=BASE, api_key="secret")
    with pytest.raises(NotFoundError):
        t.request("GET", "/api/v1/experiments/x")


@respx.mock
def test_retries_then_succeeds_on_429():
    respx.get(f"{BASE}/api/v1/results").mock(side_effect=[
        httpx.Response(429, json={"error": "rate", "message": "slow down",
                                  "status_code": 429, "request_id":
                                  "66666666-6666-6666-6666-666666666666"}),
        httpx.Response(200, json=[]),
    ])
    t = LiveTransport(base_url=BASE, api_key="secret", max_retries=2)
    assert t.request("GET", "/api/v1/results") == []


def test_missing_key_raises_auth_error():
    t = LiveTransport(base_url=BASE, api_key=None)
    with pytest.raises(AuthError):
        t.request("GET", "/api/v1/experiments")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_live_transport.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'adaptyv.live_transport'`.

- [ ] **Step 3: Write LiveTransport**

`adaptyv/live_transport.py`:
```python
from __future__ import annotations

import time
from typing import Any

import httpx

from adaptyv.errors import AuthError, TransportError, error_for_status

_RETRY_STATUS = {429, 500, 502, 503, 504}


class LiveTransport:
    def __init__(self, base_url: str, api_key: str | None, *, max_retries: int = 2,
                 timeout: float = 30.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._max_retries = max_retries
        self._client = httpx.Client(timeout=timeout)

    def request(self, method: str, path: str, *, params: dict | None = None,
                json: dict | None = None) -> Any:
        if not self._api_key and not path.startswith("/api/v1/info/health"):
            raise AuthError("No API key. Pass api_key= or set ADAPTYV_API_KEY, "
                            "or use AdaptyvClient(mock=True).", status_code=401)
        url = f"{self._base_url}{path}"
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                resp = self._client.request(method, url, params=params, json=json,
                                            headers=headers)
            except httpx.HTTPError as exc:  # network-level failure
                last_exc = TransportError(f"network error: {exc}")
                if attempt < self._max_retries:
                    time.sleep(0.2 * (attempt + 1))
                    continue
                raise last_exc
            if resp.status_code in _RETRY_STATUS and attempt < self._max_retries:
                time.sleep(0.2 * (attempt + 1))
                continue
            if resp.status_code >= 400:
                raise _to_error(resp)
            return resp.json() if resp.content else None
        raise last_exc or TransportError("request failed")


def _to_error(resp: httpx.Response):
    message = f"HTTP {resp.status_code}"
    request_id = None
    try:
        body = resp.json()
        message = body.get("message", message)
        request_id = body.get("request_id")
    except Exception:
        pass
    return error_for_status(resp.status_code, message, request_id)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_live_transport.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add adaptyv/live_transport.py tests/test_live_transport.py
git commit -m "feat: add LiveTransport with retry and typed error mapping"
```

---

### Task 7: Minimal Typer CLI

**Files:**
- Create: `adaptyv/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `AdaptyvClient` (Task 4).
- Produces: `adaptyv.cli.app` (Typer app) with commands `experiments list [--mock]`
  and `results get <id> [--mock]`, printing a concise summary. `--mock` defaults True
  so the CLI is runnable with no key.

- [ ] **Step 1: Write the failing test** (uses Typer's `CliRunner`)

`tests/test_cli.py`:
```python
from typer.testing import CliRunner

from adaptyv.cli import app

runner = CliRunner()


def test_experiments_list_mock():
    result = runner.invoke(app, ["experiments", "list"])
    assert result.exit_code == 0
    assert "EXP-1001" in result.stdout
    assert "complete" in result.stdout


def test_results_get_mock():
    result = runner.invoke(app, ["results", "get", "aaaaaaaa-0000-0000-0000-000000000001"])
    assert result.exit_code == 0
    assert "kd" in result.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cli.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'adaptyv.cli'`.

- [ ] **Step 3: Write the CLI**

`adaptyv/cli.py`:
```python
from __future__ import annotations

import typer

from adaptyv import AdaptyvClient

app = typer.Typer(help="Adaptyv Foundry SDK CLI")
experiments_app = typer.Typer(help="Experiment commands")
results_app = typer.Typer(help="Result commands")
app.add_typer(experiments_app, name="experiments")
app.add_typer(results_app, name="results")


def _client(mock: bool) -> AdaptyvClient:
    return AdaptyvClient(mock=mock)


@experiments_app.command("list")
def experiments_list(mock: bool = typer.Option(True, help="Use mock data (no key).")):
    for e in _client(mock).experiments.list():
        typer.echo(f"{e.code}\t{e.status.value}\t{e.name or ''}")


@results_app.command("get")
def results_get(result_id: str,
                mock: bool = typer.Option(True, help="Use mock data (no key).")):
    result = _client(mock).results.get(result_id)
    typer.echo(f"{result.title}")
    for s in result.summary:
        typer.echo(f"  {s.readout}={s.value} {s.value_units or ''} ({s.sequence})")


if __name__ == "__main__":
    app()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_cli.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Full suite green + commit**

Run: `python -m pytest -q`
Expected: PASS (all tasks' tests green).

```bash
git add adaptyv/cli.py tests/test_cli.py
git commit -m "feat: add minimal Typer CLI (experiments list, results get)"
```

---

## Phase 1 Definition of Done

- `pip install -e ".[dev]"` succeeds.
- `python -m pytest -q` is fully green.
- `python -c "from adaptyv import AdaptyvClient; print(AdaptyvClient(mock=True).experiments.list()[0].code)"` prints `EXP-1001`.
- `adaptyv experiments list` prints the mock experiments with no API key.
- Contract test guarantees every fixture validates against the real pydantic models.

**Next phase (written just-in-time):** Phase 2 — Governance layer (hash-chained
audit log + approval state machine), then Phase 3 — ExperimentWatcher agent
(anomaly detector + email drafter) with the anomalous fixtures.
```
