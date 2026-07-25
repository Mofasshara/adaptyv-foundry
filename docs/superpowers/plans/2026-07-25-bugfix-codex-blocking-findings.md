# Bugfix: Codex Post-Phase-5 Review — BLOCKING Findings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the 3 confirmed BLOCKING defects from the post-Phase-5 external (Codex) whole-project review, independently re-verified against the live code before this plan was written. SHOULD-FIX and NICE-TO-HAVE findings from that review are explicitly out of scope — logged to `ROADMAP.md` as known follow-ups, not touched here.

**Architecture:** Three independent, surgical fixes touching disjoint code paths — no shared design decision links them beyond "make an existing documented guarantee actually hold under a case the current code doesn't cover."

**Tech Stack:** Same as the rest of the repo — Python 3.11+/pydantic v2/pytest for Tasks 1 and 3, plus TypeScript/Zod/node:test for the MCP-facing half of Task 1.

## Global Constraints

- Every fix must have a test that FAILS on the pre-fix code and PASSES after the fix (TDD; confirm RED before GREEN).
- Do not touch anything outside the 3 findings below — no drive-by refactors, no fixing SHOULD-FIX items even if tempting.
- `evals/` may import from `adaptyv/*`; `adaptyv/*` must never import from `evals/`.
- No live Anthropic API calls introduced anywhere in tests.
- Preserve all currently-passing tests (144 Python + 14 TypeScript) — a fix that breaks an existing test is not done.

---

### Task 1: Experiment creation/cost-estimate request schema (dict-keyed `sequences`) + expose `method`/`n_replicates`

**Files:**
- Modify: `adaptyv/models.py:96-107` (add `SequenceInput`), `adaptyv/models.py:262-268` (`ExperimentSpec`)
- Modify: `adaptyv/bridge.py:26-27, 44-51, 69-74` (`_sequence_entries` → `_sequences_by_name`, both ops)
- Modify: `mcp/src/tools/experiments.ts:38-57` (`createCreateExperimentWithSequencesTool`)
- Modify: `mcp/src/tools/results.ts:19-32` (`createEstimateCostTool`)
- Modify: `tests/test_experiment_writes.py`, `mcp/src/tools/experiments.test.ts`, `mcp/src/tools/results.test.ts`
- Create: `tests/test_experiment_spec_wire_shape.py`

**Context:** The real Foundry OpenAPI spec (`tests/data/openapi.json`, schema `ExperimentSpecCommon`) defines `sequences` as an **object** keyed by a human-readable name, with each value being either a plain amino-acid string or a rich object (`SequenceInput`: `aa_string`, optional `control`, optional `metadata`) — this is the `SequenceValue` `oneOf`. The current `ExperimentSpec.sequences: list[SequenceEntry]` in `adaptyv/models.py` serializes as a JSON **array**, which a real Foundry API call would reject. This is the request body for BOTH `POST /experiments` (`CreateExpRequest.experiment_spec`) and `POST /experiments/cost-estimate` (`CostEstimateRequest.experiment_spec`) — same `ExperimentSpec` type, same bug, both endpoints.

Separately, `ExperimentSpecCommon.method` is **required** for `affinity`/`screening` experiment types (the model field already exists on `ExperimentSpec` but nothing upstream — the bridge op or the MCP tool — lets a caller actually supply it), and `n_replicates` (optional, not currently modeled at all) is fully inaccessible. Both must become settable end-to-end: MCP tool → bridge op → `ExperimentSpec`.

Do NOT touch `SequenceAddRequest` (used by `POST /sequences`, i.e. `adaptyv/bridge.py`'s `_op_add_sequences` and the `add_sequences` MCP tool) — that endpoint's real schema genuinely is `sequences: SequenceEntry[]` (verified against `tests/data/openapi.json`'s `SequenceAddRequest` schema), so `SequenceEntry` stays exactly as-is and that code path is not part of this bug.

**Interfaces:**
- Produces: `adaptyv.models.SequenceInput(aa_string: str, control: bool | None = None, metadata: dict[str, Any] | None = None)` — a new `_Req` model.
- Produces: `ExperimentSpec.sequences: dict[str, str | SequenceInput]` (was `list[SequenceEntry]`), plus new field `n_replicates: int | None = None`.
- Produces: `adaptyv.bridge._sequences_by_name(raw: list[dict]) -> dict[str, SequenceInput]` (replaces `_sequence_entries`, which is deleted — it is only used by `_op_create_experiment_with_sequences` and `_op_estimate_cost`; `_op_add_sequences` gets its own inline list-building call since it still needs `SequenceEntry` objects, unchanged).

- [ ] **Step 1: Write the failing wire-shape test**

Create `tests/test_experiment_spec_wire_shape.py`:

```python
import json
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from adaptyv.models import CreateExpRequest, CostEstimateRequest, ExperimentSpec, SequenceInput

SPEC = json.loads(Path("tests/data/openapi.json").read_text())
SPEC_URI = "urn:adaptyv:openapi-spec"
_REGISTRY = Registry().with_resource(SPEC_URI, Resource(contents=SPEC, specification=DRAFT202012))


def _validator(component: str) -> Draft202012Validator:
    return Draft202012Validator({"$ref": f"{SPEC_URI}#/components/schemas/{component}"},
                                registry=_REGISTRY)


def _spec():
    return ExperimentSpec(
        experiment_type="affinity",
        method="bli",
        target_id="44444444-0000-0000-0000-000000000001",
        n_replicates=3,
        sequences={
            "binder-1": SequenceInput(aa_string="MKAA", control=False),
            "control-1": "MKAAQQ",
        },
    )


def test_create_request_sequences_serializes_as_object_not_array():
    body = CreateExpRequest(name="My run", experiment_spec=_spec()).model_dump(exclude_none=True)
    assert isinstance(body["experiment_spec"]["sequences"], dict)
    assert body["experiment_spec"]["sequences"]["binder-1"] == {"aa_string": "MKAA", "control": False}
    assert body["experiment_spec"]["sequences"]["control-1"] == "MKAAQQ"


def test_create_request_body_validates_against_real_openapi_schema():
    body = CreateExpRequest(name="My run", experiment_spec=_spec()).model_dump(exclude_none=True)
    _validator("CreateExpRequest").validate(body)


def test_cost_estimate_request_body_validates_against_real_openapi_schema():
    body = CostEstimateRequest(experiment_spec=_spec()).model_dump(exclude_none=True)
    _validator("CostEstimateRequest").validate(body)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_experiment_spec_wire_shape.py -v`
Expected: FAIL — `ImportError: cannot import name 'SequenceInput'` (it doesn't exist yet).

- [ ] **Step 3: Add `SequenceInput` and fix `ExperimentSpec` in `adaptyv/models.py`**

Add immediately after the existing `SequenceEntry` class (around line 100):

```python
class SequenceInput(_R):
    aa_string: str
    control: bool | None = None
    metadata: dict[str, Any] | None = None
```

(Use `_R`, not `_Req` — it's a value nested inside a request but the project's existing convention models nested value objects with `_R`'s `extra="ignore"` tolerance; `SequenceEntry` above it already follows this convention.)

Replace the `ExperimentSpec` class (around line 262-268):

```python
class ExperimentSpec(_Req):
    experiment_type: ExperimentType
    sequences: dict[str, str | SequenceInput] = Field(default_factory=dict)
    target_id: str | None = None
    method: Method | None = None
    n_replicates: int | None = None
    antigen_concentrations: list[float] | None = None
    parameters: dict[str, Any] | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_experiment_spec_wire_shape.py -v`
Expected: PASS (all 3 tests)

- [ ] **Step 5: Fix the now-broken existing SDK test**

`tests/test_experiment_writes.py` constructs `_spec()` with the old array shape. Update it:

```python
from adaptyv import AdaptyvClient
from adaptyv.models import (CreateExpRequest, CreateExpResponse, CostEstimateRequest,
                            CostEstimateResponse, ExperimentSpec, SequenceInput)

def _spec():
    return ExperimentSpec(experiment_type="affinity", method="bli",
                          target_id="44444444-0000-0000-0000-000000000001",
                          sequences={"binder-1": SequenceInput(aa_string="MKAA")})

def test_create_returns_experiment_id():
    r = AdaptyvClient(mock=True).experiments.create(
        CreateExpRequest(name="My run", experiment_spec=_spec()))
    assert isinstance(r, CreateExpResponse) and r.experiment_id

def test_cost_estimate_returns_response():
    r = AdaptyvClient(mock=True).experiments.cost_estimate(CostEstimateRequest(experiment_spec=_spec()))
    assert isinstance(r, CostEstimateResponse)
```

Run: `python3 -m pytest tests/test_experiment_writes.py -v` — expect PASS.

- [ ] **Step 6: Commit the model fix**

```bash
git add adaptyv/models.py tests/test_experiment_spec_wire_shape.py tests/test_experiment_writes.py
git commit -m "fix: ExperimentSpec.sequences is dict-keyed per real OpenAPI schema, not a list"
```

- [ ] **Step 7: Write the failing bridge test for the new helper**

Read `tests/test_bridge.py` first to match its existing fixture/assertion style, then add:

```python
def test_create_experiment_bridge_op_sends_sequences_as_dict_keyed_by_name():
    from adaptyv.bridge import handle_request
    response = handle_request({
        "op": "create_experiment_with_sequences",
        "params": {
            "name": "My run",
            "experiment_type": "affinity",
            "method": "bli",
            "sequences": [{"aa_string": "MKAA", "name": "binder-1"},
                         {"aa_string": "MKZZ"}],
        },
    })
    assert response["ok"] is True
```

(This proves the params-to-`ExperimentSpec` construction doesn't raise — the dict-shape correctness is already proven at the model level in Step 1-4; this test proves the bridge's translation layer wires it through end-to-end without a validation error.)

- [ ] **Step 8: Run test to verify it fails**

Run: `python3 -m pytest tests/test_bridge.py -k dict_keyed -v`
Expected: FAIL — either an import error or a construction error, since `_sequences_by_name` doesn't exist yet and `_sequence_entries` still builds a list.

- [ ] **Step 9: Implement `_sequences_by_name` in `adaptyv/bridge.py`**

Replace `_sequence_entries` (lines 26-27):

```python
def _sequences_by_name(raw: list[dict]) -> dict[str, SequenceInput]:
    result: dict[str, SequenceInput] = {}
    for i, s in enumerate(raw):
        key = s.get("name") or f"seq{i + 1}"
        result[key] = SequenceInput(aa_string=s["aa_string"], control=s.get("control"))
    return result
```

Update the import (line 15): replace `SequenceEntry` with `SequenceInput` in the `create_experiment_with_sequences`/`estimate_cost` path — but `SequenceEntry` is still needed by `_op_add_sequences`, so the import line becomes:

```python
from adaptyv.models import CostEstimateRequest, CreateExpRequest, ExperimentSpec, SequenceAddRequest, SequenceEntry, SequenceInput
```

Update `_op_create_experiment_with_sequences` (lines 44-51):

```python
def _op_create_experiment_with_sequences(params: dict) -> Any:
    client = _client(params)
    spec = ExperimentSpec(experiment_type=params["experiment_type"],
                          sequences=_sequences_by_name(params.get("sequences", [])),
                          target_id=params.get("target_id"),
                          method=params.get("method"),
                          n_replicates=params.get("n_replicates"))
    request = CreateExpRequest(name=params["name"], experiment_spec=spec,
                               skip_draft=params.get("skip_draft"))
    return client.experiments.create(request).model_dump(mode="json")
```

Update `_op_estimate_cost` (lines 69-74):

```python
def _op_estimate_cost(params: dict) -> Any:
    client = _client(params)
    spec = ExperimentSpec(experiment_type=params["experiment_type"],
                          sequences=_sequences_by_name(params.get("sequences", [])),
                          target_id=params.get("target_id"),
                          method=params.get("method"),
                          n_replicates=params.get("n_replicates"))
    return client.experiments.cost_estimate(CostEstimateRequest(experiment_spec=spec)).model_dump(mode="json")
```

`_op_add_sequences` (lines 54-58) is unchanged — it keeps building `list[SequenceEntry]` via its own inline list comprehension, since that endpoint's real schema genuinely wants an array:

```python
def _op_add_sequences(params: dict) -> Any:
    client = _client(params)
    request = SequenceAddRequest(
        experiment_code=params["experiment_code"],
        sequences=[SequenceEntry(aa_string=s["aa_string"], name=s.get("name")) for s in params.get("sequences", [])])
    return client.sequences.add(request).model_dump(mode="json")
```

- [ ] **Step 10: Run test to verify it passes**

Run: `python3 -m pytest tests/test_bridge.py -v`
Expected: PASS, all tests in the file.

- [ ] **Step 11: Commit**

```bash
git add adaptyv/bridge.py tests/test_bridge.py
git commit -m "fix: bridge translates flat sequence list into name-keyed dict for ExperimentSpec"
```

- [ ] **Step 12: Update the MCP tools' Zod schemas and add `method`/`n_replicates`**

In `mcp/src/tools/experiments.ts`, update `createCreateExperimentWithSequencesTool`'s `inputSchema` (lines 43-52) to add `method` and `n_replicates`:

```typescript
inputSchema: {
  name: z.string().describe("Human-readable name for the experiment"),
  experiment_type: z.enum(EXPERIMENT_TYPES),
  method: z.enum(["bli", "spr"]).optional()
    .describe("Measurement method — required by the API for affinity/screening experiments"),
  n_replicates: z.number().int().optional().describe("Number of technical replicates"),
  sequences: z.array(z.object({
    aa_string: z.string().describe("Amino acid sequence"),
    name: z.string().optional(),
  })),
  target_id: z.string().optional().describe("UUID of a catalog target antigen, for binding assays"),
  skip_draft: z.boolean().optional(),
},
```

In `mcp/src/tools/results.ts`, update `createEstimateCostTool`'s `inputSchema` (lines 24-28) the same way:

```typescript
inputSchema: {
  experiment_type: z.enum(EXPERIMENT_TYPES),
  method: z.enum(["bli", "spr"]).optional()
    .describe("Measurement method — required by the API for affinity/screening experiments"),
  n_replicates: z.number().int().optional().describe("Number of technical replicates"),
  sequences: z.array(z.object({ aa_string: z.string(), name: z.string().optional() })).optional(),
  target_id: z.string().optional(),
},
```

- [ ] **Step 13: Write the failing MCP tests (before Step 12's edit, for a true RED)**

Do this step BEFORE Step 12 if you want genuine TDD ordering — write both tests first, confirm they fail against the current (unedited) `inputSchema`s, then make the Step 12 edit.

In `mcp/src/tools/experiments.test.ts`, add immediately after the existing `create_experiment_with_sequences tool forwards name, type, and sequences to the bridge` test:

```typescript
test("create_experiment_with_sequences tool forwards method and n_replicates to the bridge", async () => {
  const calls: { op: string; params?: Record<string, unknown> }[] = [];
  const bridge = {
    call: async (op: string, params?: Record<string, unknown>) => {
      calls.push({ op, params });
      return { experiment_id: "99999999-9999-9999-9999-999999999999" };
    },
  } as any;
  const tool = createCreateExperimentWithSequencesTool(bridge);

  await tool.handler({
    name: "My run",
    experiment_type: "affinity",
    method: "bli",
    n_replicates: 3,
    sequences: [{ aa_string: "MKAA" }],
  });

  assert.equal(calls[0].params?.method, "bli");
  assert.equal(calls[0].params?.n_replicates, 3);
});
```

In `mcp/src/tools/results.test.ts`, add immediately after the existing `estimate_cost tool forwards experiment_type and sequences to the bridge` test:

```typescript
test("estimate_cost tool forwards method and n_replicates to the bridge", async () => {
  const calls: any[] = [];
  const bridge = { call: async (op: string, params?: any) => { calls.push({ op, params }); return { breakdown: {} }; } } as any;
  const tool = createEstimateCostTool(bridge);

  await tool.handler({ experiment_type: "affinity", method: "bli", n_replicates: 3,
                       sequences: [{ aa_string: "MKAA" }] });

  assert.equal(calls[0].params.method, "bli");
  assert.equal(calls[0].params.n_replicates, 3);
});
```

- [ ] **Step 14: Run tests to verify they fail**

Run: `cd mcp && npm test`
Expected: FAIL on both new tests — `method`/`n_replicates` are `undefined` in `calls[0].params` because the current `inputSchema`s (pre-Step-12) don't declare those fields, so the MCP framework's Zod validation strips them before the handler ever sees them.

- [ ] **Step 15: Run tests to verify they pass**

Run: `cd mcp && npm test`
Expected: PASS, all tests (should be 16 now, up from 14).

- [ ] **Step 16: Commit**

```bash
git add mcp/src/tools/experiments.ts mcp/src/tools/experiments.test.ts mcp/src/tools/results.ts mcp/src/tools/results.test.ts
git commit -m "feat: expose method and n_replicates on experiment creation/cost-estimate MCP tools"
```

---

### Task 2: Close the hallucination-guard gaps — subject bypass + malformed placeholder blind spot

**Files:**
- Modify: `adaptyv/agents/email.py` (lines 17, 52-59, 91-93)
- Modify: `evals/guards.py` (line 9)
- Modify: `tests/test_email_drafter.py`, `tests/test_guards.py`

**Context:** Two independent gaps in the "Claude can never get a raw number or malformed placeholder into a persisted draft" guarantee:
1. `EmailDrafter.draft()` (`adaptyv/agents/email.py:91-93`) runs `substitute_facts()` on `draft.body` but returns `draft.subject` completely unvalidated — any placeholder (well-formed or not) in the subject line passes straight through.
2. `_PLACEHOLDER = re.compile(r"\{\{([\w-]+)\}\}")` (identical in both `adaptyv/agents/email.py:17` and `evals/guards.py:9`) only matches braces containing word-characters/hyphens. A malformed construct like `{{bad token}}` (a space) or `{{fact/1}}` (a slash) doesn't match at all — `_PLACEHOLDER.sub()` leaves it completely untouched: not substituted, not raised on, invisible to `guard_no_leftover_placeholder_syntax` too, since it uses the exact same regex.

**Interfaces:**
- Produces: `adaptyv.agents.email.substitute_facts` — unchanged signature, but now raises `UnresolvedPlaceholderError` on ANY malformed `{{...}}` construct, not just well-formed-but-unknown ones.
- Produces: `EmailDrafter.draft()` — now validates/substitutes both `subject` and `body` before returning.
- Produces: `evals.guards.guard_no_leftover_placeholder_syntax` — unchanged signature, now detects any `{{...}}` construct as leftover, not just `[\w-]+`-shaped ones.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_email_drafter.py`:

```python
def test_substitute_facts_raises_on_malformed_placeholder_with_space():
    # Regression test: a placeholder-shaped construct that ISN'T [\w-]+ (e.g.
    # contains a space) must still be caught, not silently left in the output
    # untouched and unraised.
    with pytest.raises(UnresolvedPlaceholderError):
        substitute_facts("Kd was {{bad token}}.", {"kd_mean_binder-1": "1.20e-09 M"})


def test_drafter_validates_subject_not_just_body():
    # Regression test: the "never emit a raw placeholder" guarantee must cover
    # the subject line too, not only the body.
    fake_response = _FakeParseResponse(EmailDraftSchema(
        subject="Results: {{not_a_real_fact}}", body="no tokens here"))
    drafter = EmailDrafter(client=_FakeClient(fake_response))
    with pytest.raises(UnresolvedPlaceholderError):
        drafter.draft(_result(), findings=[])


def test_drafter_substitutes_placeholder_in_subject_when_valid():
    fake_response = _FakeParseResponse(EmailDraftSchema(
        subject="Kd result: {{kd_mean_binder-1}}", body="See details above."))
    drafter = EmailDrafter(client=_FakeClient(fake_response))
    out = drafter.draft(_result(), findings=[])
    assert out.subject == "Kd result: 1.20e-09 M"
```

Add to `tests/test_guards.py` (read the file first to match its existing fixture/import style):

```python
def test_guard_no_leftover_placeholder_syntax_catches_malformed_construct():
    from evals.guards import guard_no_leftover_placeholder_syntax
    violations = guard_no_leftover_placeholder_syntax("Kd was {{bad token}}.")
    assert violations
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_email_drafter.py tests/test_guards.py -v -k "malformed or subject_not_just_body or in_subject_when_valid or catches_malformed"`
Expected: FAIL on all 4 new tests (space-containing placeholder currently passes through silently; subject is currently never validated).

- [ ] **Step 3: Fix `adaptyv/agents/email.py`**

Replace line 17:

```python
_PLACEHOLDER = re.compile(r"\{\{(.+?)\}\}")
_VALID_FACT_ID = re.compile(r"^[\w-]+$")
```

Replace `substitute_facts` (lines 52-59):

```python
def substitute_facts(body: str, fact_sheet: dict[str, str]) -> str:
    def _replace(m: re.Match) -> str:
        fact_id = m.group(1)
        if not _VALID_FACT_ID.match(fact_id) or fact_id not in fact_sheet:
            raise UnresolvedPlaceholderError(
                f"drafter emitted unknown placeholder '{{{{{fact_id}}}}}' — not in the fact sheet")
        return fact_sheet[fact_id]
    return _PLACEHOLDER.sub(_replace, body)
```

Replace the return in `EmailDrafter.draft()` (lines 91-93):

```python
        draft = response.parsed_output
        resolved_subject = substitute_facts(draft.subject, fact_sheet)
        resolved_body = substitute_facts(draft.body, fact_sheet)
        return EmailDraftSchema(subject=resolved_subject, body=resolved_body)
```

- [ ] **Step 4: Fix `evals/guards.py`**

Replace line 9:

```python
_PLACEHOLDER = re.compile(r"\{\{(.+?)\}\}")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_email_drafter.py tests/test_guards.py -v`
Expected: PASS, every test in both files (including all pre-existing ones — `{{kd_mean_binder-1}}`-style well-formed tokens still match `.+?` fine, since it's a strict superset of `[\w-]+`).

- [ ] **Step 6: Run the full suite and the offline eval to check for regressions**

Run: `python3 -m pytest -q` — expect all passing (144 + the new tests from this task and Task 1).
Run: `make eval` — expect `3 cases, 0 violation(s)`, exit 0.

- [ ] **Step 7: Commit**

```bash
git add adaptyv/agents/email.py evals/guards.py tests/test_email_drafter.py tests/test_guards.py
git commit -m "fix: validate email subject through substitute_facts; widen placeholder detection past [\\w-]+"
```

---

### Task 3: Atomic Watcher idempotency (draft + audit + processed-marker in one transaction)

**Files:**
- Modify: `adaptyv/governance/approval.py:27-47` (`create_draft`)
- Modify: `adaptyv/agents/watcher.py:25-56` (`run`, remove `_mark_processed`)
- Modify: `tests/test_watcher.py`, `tests/test_approval_store.py`

**Context:** `Watcher.run()` currently creates a draft (which commits atomically with its audit entry, inside `ApprovalStore.create_draft()`) and THEN, as a separate later statement OUTSIDE the surrounding `try/except`, inserts a row into `watcher_processed` and commits again. Two bugs follow from this:
1. **Non-atomic idempotency:** a crash between the two commits leaves a draft with no processed-marker; the next run doesn't see it as processed and creates a duplicate draft for the same result.
2. **Batch-fatal marker failure:** because `_mark_processed()` sits after the `try/except` that isolates per-result failures, if it ever raises (e.g. a `PRIMARY KEY` collision from two watchers racing on the same key), the exception isn't caught by that `try/except` at all — it propagates out of `run()` entirely, aborting every remaining experiment/result in the batch. This is the same failure shape (one bad item takes down the whole batch) already fixed twice elsewhere in this project (Phase 3's `Watcher`, Phase 4's bridge dispatch) — this is a variant that survived because it's a *different statement* in the *same function* that was outside the guarded region.

The fix: give `ApprovalStore.create_draft()` an optional `on_commit` hook invoked inside the same transaction as the draft insert and audit record (so it commits or rolls back atomically with them), and have `Watcher` use it to write the `watcher_processed` row. Because `on_commit` now runs *inside* the same `_do()` that `create_draft()`'s call site is wrapped by Watcher's existing per-result `try/except`, any failure in the marker write rolls back the whole draft+audit+marker transaction together AND is caught by the existing per-result isolation — both bugs close with one change.

**Interfaces:**
- Consumes: `adaptyv.governance.approval.ApprovalStore._mutate_and_record(fn)` — unchanged, already commits-or-rolls-back `fn` as one transaction.
- Produces: `ApprovalStore.create_draft(..., on_commit: Callable[[str], None] | None = None) -> Draft` — new optional keyword parameter, called with the generated `draft_id` from inside the same transaction, right after the audit record.
- Consumes (by Watcher): the new `on_commit` parameter.

- [ ] **Step 1: Write the failing atomicity test**

Read `tests/test_approval_store.py` first to match its fixture/connection setup style, then add:

```python
def test_create_draft_on_commit_hook_runs_in_the_same_transaction():
    conn = connect()
    store = ApprovalStore(conn, AuditLog(conn))
    calls = []

    draft = store.create_draft(
        "exp-1", "body text", created_by=Actor(kind="agent", id="watcher"),
        on_commit=lambda draft_id: calls.append(draft_id))

    assert calls == [draft.draft_id]


def test_create_draft_on_commit_failure_rolls_back_the_draft_too():
    conn = connect()
    store = ApprovalStore(conn, AuditLog(conn))

    def _boom(draft_id):
        raise RuntimeError("marker write failed")

    with pytest.raises(RuntimeError):
        store.create_draft("exp-1", "body text",
                           created_by=Actor(kind="agent", id="watcher"), on_commit=_boom)

    # The draft must NOT exist -- on_commit failing must roll back the whole
    # transaction, not leave an orphaned draft with no marker.
    assert store.list() == []
```

(Check the file's existing imports for `connect`, `AuditLog`, `Actor`, `pytest` and reuse them — don't re-import if already present.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_approval_store.py -v -k on_commit`
Expected: FAIL — `TypeError: create_draft() got an unexpected keyword argument 'on_commit'`.

- [ ] **Step 3: Add `on_commit` to `ApprovalStore.create_draft`**

Add `from typing import Callable` to the top imports of `adaptyv/governance/approval.py` (alongside the existing `from __future__ import annotations` etc.).

Replace `create_draft` (lines 27-47):

```python
    def create_draft(self, experiment_id: str, body: str, *, result_id: str | None = None,
                     anomalies: list[AnomalyFinding] | None = None, created_by: Actor,
                     on_commit: Callable[[str], None] | None = None) -> Draft:
        anomalies = anomalies or []
        draft_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()

        def _do() -> None:
            self._conn.execute(
                """INSERT INTO drafts
                   (draft_id,experiment_id,result_id,status,body,anomalies,created_by,created_at,anomalies_acknowledged)
                   VALUES (?,?,?,?,?,?,?,?,0)""",
                (draft_id, experiment_id, result_id, DraftStatus.PENDING_REVIEW.value, body,
                 json.dumps([a.model_dump(mode="json") for a in anomalies]),
                 json.dumps(created_by.model_dump(mode="json")), created_at),
            )
            self._audit.record(created_by, "draft.create", "draft", draft_id, "pending_review",
                               {"experiment_id": experiment_id, "result_id": result_id,
                                "anomaly_count": len(anomalies)})
            if on_commit is not None:
                on_commit(draft_id)

        self._mutate_and_record(_do)
        return self.get(draft_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_approval_store.py -v`
Expected: PASS, every test in the file.

- [ ] **Step 5: Commit**

```bash
git add adaptyv/governance/approval.py tests/test_approval_store.py
git commit -m "feat: create_draft accepts an on_commit hook, run inside the same transaction"
```

- [ ] **Step 6: Write the failing Watcher atomicity test**

Add to `tests/test_watcher.py`:

```python
def test_mark_processed_failure_is_isolated_not_batch_fatal():
    # Regression test: if writing the watcher_processed marker fails (e.g. a
    # genuine race between two watchers on the same key), that failure must
    # be caught by the SAME per-result try/except that isolates a bad
    # drafter -- not escape run() and abort the whole batch.
    watcher, store = _make_watcher()

    # Pre-insert a colliding marker row so the real INSERT inside on_commit
    # collides with a UNIQUE/PRIMARY KEY violation for the first result Watcher
    # will process.
    first_result = watcher._client.experiments.results("11111111-1111-1111-1111-111111111111")[0]
    key = f"11111111-1111-1111-1111-111111111111:{first_result.id}:{watcher._drafter.model}"
    watcher._conn.execute(
        "INSERT INTO watcher_processed (key, draft_id) VALUES (?, ?)", (key, "some-other-draft-id"))
    watcher._conn.commit()

    drafts = watcher.run(experiment_ids=[
        "11111111-1111-1111-1111-111111111111",
        "33333333-3333-3333-3333-333333333333",
    ])

    # The colliding experiment's result is skipped as already-processed (the
    # pre-inserted row makes _already_processed() return True for it) --
    # this test is really about proving run() doesn't crash and the SECOND
    # experiment still produces a draft.
    assert len(drafts) == 1
    assert drafts[0].experiment_id == "33333333-3333-3333-3333-333333333333"


def test_draft_and_processed_marker_commit_together():
    # Regression test for the atomicity bug: after a successful run, every
    # draft Watcher created has a corresponding watcher_processed row -- they
    # cannot exist independently of each other.
    watcher, store = _make_watcher()
    drafts = watcher.run()
    assert drafts
    for draft in drafts:
        rows = watcher._conn.execute(
            "SELECT 1 FROM watcher_processed WHERE draft_id=?", (draft.draft_id,)).fetchall()
        assert len(rows) == 1
```

- [ ] **Step 7: Run tests to verify they fail (or pass trivially before the fix — confirm the intent)**

Run: `python3 -m pytest tests/test_watcher.py -v -k "isolated_not_batch_fatal or commit_together"`

`test_draft_and_processed_marker_commit_together` may already pass on the pre-fix code in the success path (both writes still happen, just non-atomically) — that's fine, it's a regression guard for the fix, not required to be RED. `test_mark_processed_failure_is_isolated_not_batch_fatal` MUST fail on pre-fix code: the pre-fix `_mark_processed()` call sits outside the `try/except`, so the forced `IntegrityError` from the pre-inserted colliding row will propagate out of `run()` uncaught, crashing the whole test with an unhandled exception rather than returning cleanly.

- [ ] **Step 8: Fix `adaptyv/agents/watcher.py`**

Replace the whole file body from `run` through `_mark_processed` (lines 25-56):

```python
    def run(self, experiment_ids: list[str] | None = None) -> list[Draft]:
        if experiment_ids is None:
            experiment_ids = [e.id for e in self._client.experiments.list()]
        created: list[Draft] = []
        for experiment_id in experiment_ids:
            for result in self._client.experiments.results(experiment_id):
                key = f"{experiment_id}:{result.id}:{self._drafter.model}"
                if self._already_processed(key):
                    continue
                try:
                    findings = self._detector.detect(result)
                    email = self._drafter.draft(result, findings)
                    body = f"Subject: {email.subject}\n\n{email.body}"
                    draft = self._store.create_draft(
                        experiment_id, body, result_id=result.id, anomalies=findings,
                        created_by=Actor(kind="agent", id="watcher"),
                        on_commit=lambda draft_id, key=key: self._conn.execute(
                            "INSERT INTO watcher_processed (key, draft_id) VALUES (?, ?)",
                            (key, draft_id)))
                except Exception as exc:  # noqa: BLE001 - isolate one bad result, keep the batch alive
                    self.errors.append((experiment_id, result.id, exc))
                    continue
                created.append(draft)
        return created

    def _already_processed(self, key: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM watcher_processed WHERE key=?", (key,)).fetchone()
        return row is not None
```

(`_mark_processed` is deleted entirely — its one job is now done via `on_commit` inside `create_draft`.)

- [ ] **Step 9: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_watcher.py -v`
Expected: PASS, every test in the file, including all pre-existing ones (`test_rerun_does_not_duplicate_drafts`, `test_one_bad_result_does_not_abort_batch`, `test_rerun_across_new_connection_to_same_file_does_not_duplicate`, etc.).

- [ ] **Step 10: Run the full suite**

Run: `python3 -m pytest -q`
Expected: all passing (144 original + new tests from Tasks 1, 2, 3).

- [ ] **Step 11: Commit**

```bash
git add adaptyv/agents/watcher.py tests/test_watcher.py
git commit -m "fix: watcher_processed marker commits atomically with the draft+audit write"
```
