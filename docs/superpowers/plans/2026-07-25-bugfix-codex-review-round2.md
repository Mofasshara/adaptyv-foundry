# Bugfix: Codex Round-2 Review Findings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix everything a second, independent Codex review found after the first bugfix cycle: (1) a genuine regression in the previous fix — `_sequences_by_name` silently drops sequences on a name collision; (2) the email hallucination guard still lets raw, un-placeholder'd numbers (and a couple of malformed-placeholder edge cases) through; (3) a design smell in the `on_commit` hook — misleading name, and an unenforced same-connection precondition for its atomicity guarantee to actually hold.

**Architecture:** Three independent fixes. Task 1 is bridge-layer input validation. Task 2 extends the hallucination-prevention guarantee with a new grounded-numbers check, shared between production code and the offline eval guard (closing the same "shared regex blind spot" bug class this project has hit twice before). Task 3 is a rename + a defensive precondition check.

**Tech Stack:** Python 3.11+/pydantic v2/pytest — no TypeScript changes in this plan.

## Global Constraints

- Every fix must have a test that FAILS on the pre-fix code and PASSES after the fix (TDD; confirm RED before GREEN).
- Do not touch anything outside the 3 items below.
- `evals/` may import from `adaptyv/*`; `adaptyv/*` must never import from `evals/`.
- No live Anthropic API calls introduced anywhere in tests.
- Preserve all currently-passing tests (156 Python + 16 TypeScript) — a fix that breaks an existing test is not done.
- Anomaly evidence text (`AnomalyFinding.evidence`) legitimately contains numbers (replicate counts, kd values in scientific notation) that the drafter is instructed to echo directly ("Use the qualitative details... anomaly notes... directly as given") — any new number-grounding check MUST treat numbers appearing in evidence text as grounded, not just numbers in the fact sheet. Getting this wrong breaks legitimate anomaly-reporting emails, not just hallucinated ones.

---

### Task 1: Bridge rejects colliding sequence names instead of silently dropping one

**Files:**
- Modify: `adaptyv/bridge.py:26-31` (`_sequences_by_name`)
- Modify: `tests/test_bridge.py`

**Context:** `_sequences_by_name()` (added in the previous bugfix cycle to translate a flat list of sequences into the name-keyed dict the real Foundry API requires) builds its result dict with `result[key] = SequenceInput(...)` where `key` is either an explicit name or a generated `seq{i+1}` fallback. If two input sequences share a name (or an unnamed sequence's generated key collides with an explicitly-named one later in the list), the second one silently overwrites the first in the dict — one of the user's submitted sequences vanishes from the actual API request with no error, no warning. Reproduced directly:
```python
_sequences_by_name([{"aa_string": "AAA", "name": "dup"}, {"aa_string": "BBB", "name": "dup"}])
# -> {'dup': SequenceInput(aa_string='BBB', ...)}  -- AAA is gone
```
This is a genuine regression introduced by the previous fix (the old list-based representation couldn't lose data this way). The existing test for this function (`tests/test_bridge.py`, `test_create_experiment_bridge_op_sends_sequences_as_dict_keyed_by_name`) only asserts `response["ok"] is True` — it doesn't inspect what was actually sent, so it wouldn't catch this even with colliding input.

The fix: reject ambiguous input outright rather than guess which sequence to keep or silently rename it — this is a real lab-ops action (submitting sequences to be synthesized/tested), and silently renaming a user's chosen sequence name changes what's sent to the API in a way they didn't ask for.

**Interfaces:**
- Produces: `adaptyv.bridge._sequences_by_name(raw: list[dict]) -> dict[str, SequenceInput]` — unchanged signature, now raises `BridgeError` on any name collision (explicit or generated-key).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_bridge.py` (check the file's existing imports first — `BridgeError` and `handle_request` should already be importable from `adaptyv.bridge`):

```python
def test_sequences_by_name_rejects_duplicate_explicit_names():
    from adaptyv.bridge import _sequences_by_name, BridgeError
    with pytest.raises(BridgeError):
        _sequences_by_name([{"aa_string": "AAA", "name": "dup"}, {"aa_string": "BBB", "name": "dup"}])


def test_sequences_by_name_rejects_unnamed_collision_with_generated_key():
    # First sequence has no name -> generated key "seq1". Second sequence is
    # explicitly named "seq1" -> collides with the generated key.
    from adaptyv.bridge import _sequences_by_name, BridgeError
    with pytest.raises(BridgeError):
        _sequences_by_name([{"aa_string": "AAA"}, {"aa_string": "BBB", "name": "seq1"}])


def test_create_experiment_bridge_op_rejects_duplicate_sequence_names():
    response = handle_request({
        "op": "create_experiment_with_sequences",
        "params": {
            "name": "My run", "experiment_type": "affinity", "method": "bli",
            "sequences": [{"aa_string": "AAA", "name": "dup"}, {"aa_string": "BBB", "name": "dup"}],
        },
    })
    assert response["ok"] is False
    assert response["error"]["type"] == "BridgeError"
```

(Add `import pytest` to the top of `tests/test_bridge.py` if it isn't already imported — check first.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `. .venv/bin/activate && python3 -m pytest tests/test_bridge.py -v -k "duplicate or collision"`
Expected: FAIL — `_sequences_by_name` currently returns a dict silently (no exception), so `pytest.raises(BridgeError)` fails; the bridge op currently returns `{"ok": True, ...}` with one sequence silently dropped.

- [ ] **Step 3: Fix `_sequences_by_name` in `adaptyv/bridge.py`**

Replace lines 26-31:

```python
def _sequences_by_name(raw: list[dict]) -> dict[str, SequenceInput]:
    result: dict[str, SequenceInput] = {}
    for i, s in enumerate(raw):
        key = s.get("name") or f"seq{i + 1}"
        if key in result:
            raise BridgeError(f"duplicate sequence name '{key}' -- each sequence must have a unique name")
        result[key] = SequenceInput(aa_string=s["aa_string"], control=s.get("control"))
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_bridge.py -v`
Expected: PASS, every test in the file.

- [ ] **Step 5: Run the full suite**

Run: `python3 -m pytest -q`
Expected: all passing (156 + 3 new).

- [ ] **Step 6: Commit**

```bash
git add adaptyv/bridge.py tests/test_bridge.py
git commit -m "fix: reject colliding sequence names instead of silently dropping one"
```

---

### Task 2: Production-time number-grounding guard + close remaining placeholder regex gaps

**Files:**
- Modify: `adaptyv/errors.py` (add `UngroundedNumberError`)
- Modify: `adaptyv/agents/email.py` (add `grounded_numbers`, `find_ungrounded_numbers`; enforce in `draft()`; fix `_PLACEHOLDER` regex)
- Modify: `evals/guards.py` (delegate `guard_all_numbers_grounded` to the shared function; fix `_PLACEHOLDER` regex)
- Modify: `evals/run_eval.py` (pass `findings` into `guard_all_numbers_grounded`)
- Modify: `tests/test_email_drafter.py`, `tests/test_guards.py`

**Context:** Two remaining gaps in the "Claude can never emit a raw number or malformed placeholder into a persisted draft" guarantee, found by re-testing after the previous fix:

1. **Raw numbers with no `{{...}}` at all bypass everything.** `substitute_facts()` only ever touches text inside `{{...}}` spans — plain prose like `"Subject: Results 42"` or `"Model says Kd 9.99e-09 M"` has no braces at all, so it's returned completely unchanged, no exception, no check. This needs a genuinely new mechanism: after substitution, scan the final subject+body text for any number-shaped token and verify every one traces to either a fact-sheet value OR text that appeared verbatim in the anomaly findings' `evidence` field (the only two sources of grounded numeric truth given to the drafter). See the Global Constraints note above — anomaly evidence numbers (replicate counts, kd values) are legitimately echoed by the drafter and must NOT be flagged.

2. **The widened placeholder regex still has two blind spots.** `_PLACEHOLDER = re.compile(r"\{\{(.+?)\}\}")` requires at least one character between the braces (`.+?`, not `.*?`), so a literal `{{}}` (empty) doesn't match at all and passes through untouched. And `.` doesn't match newlines by default, so a multiline construct like `"{{bad\ntoken}}"` also doesn't match as a single span and passes through untouched. Both need the regex widened to `\{\{(.*?)\}\}` with `re.DOTALL`.

**Interfaces:**
- Produces: `adaptyv.errors.UngroundedNumberError(AgentError)` — new exception, same style as `UnresolvedPlaceholderError`.
- Produces: `adaptyv.agents.email.grounded_numbers(fact_sheet: dict[str, str], findings: list[AnomalyFinding]) -> set[str]` — every number appearing in a fact-sheet value or in any finding's evidence text.
- Produces: `adaptyv.agents.email.find_ungrounded_numbers(text: str, grounded: set[str]) -> list[str]` — numbers in `text` not present in `grounded`.
- Produces: `EmailDrafter.draft()` — after substitution, raises `UngroundedNumberError` if either resolved subject or body contains any ungrounded number.
- Produces: `evals.guards.guard_all_numbers_grounded(body: str, fact_sheet: dict[str, str], findings: list[AnomalyFinding] | None = None) -> list[str]` — gains an optional third parameter (defaults to `None`, treated as `[]`, so the 3 existing calls in `tests/test_guards.py` that don't pass it keep working unchanged); now delegates to `grounded_numbers`/`find_ungrounded_numbers` instead of its own separate `_SCI_NUMBER` regex, so this guard can never again drift out of sync with production's number-grounding logic.

- [ ] **Step 1: Write the failing tests**

In `tests/test_email_drafter.py`, change the existing top-level import line
`from adaptyv.errors import UnresolvedPlaceholderError` to:
```python
from adaptyv.errors import UngroundedNumberError, UnresolvedPlaceholderError
```

Then add these test functions to the file:

```python
def test_drafter_raises_on_raw_number_in_body_with_no_placeholder():
    # Regression test: a raw number with NO {{}} syntax at all bypasses
    # substitute_facts entirely -- this needs a separate grounding check.
    fake_response = _FakeParseResponse(EmailDraftSchema(
        subject="s", body="Model says Kd 9.99e-09 M"))
    drafter = EmailDrafter(client=_FakeClient(fake_response))
    with pytest.raises(UngroundedNumberError):
        drafter.draft(_result(), findings=[])


def test_drafter_raises_on_raw_number_in_subject_with_no_placeholder():
    fake_response = _FakeParseResponse(EmailDraftSchema(subject="Results 42", body="no tokens here"))
    drafter = EmailDrafter(client=_FakeClient(fake_response))
    with pytest.raises(UngroundedNumberError):
        drafter.draft(_result(), findings=[])


def test_drafter_allows_a_number_that_appears_verbatim_in_anomaly_evidence():
    # Anomaly evidence legitimately contains numbers (replicate counts, kd
    # values) that the drafter is instructed to echo directly -- these must
    # NOT be flagged as ungrounded. (AnomalyFinding is already imported at
    # the top of this file.)
    finding = AnomalyFinding(rule="missing_replicates", severity="warning",
                             evidence="binder-1 has 0 replicate(s), policy requires 2")
    fake_response = _FakeParseResponse(EmailDraftSchema(
        subject="s", body="binder-1 has 0 replicate(s), policy requires 2"))
    drafter = EmailDrafter(client=_FakeClient(fake_response))
    out = drafter.draft(_result(), findings=[finding])  # must not raise
    assert "0 replicate" in out.body


def test_drafter_allows_a_number_that_matches_a_grounded_fact_via_placeholder():
    # Existing behavior must still work: a real, grounded number substituted
    # via {{fact_id}} is fine.
    fake_response = _FakeParseResponse(EmailDraftSchema(
        subject="s", body="Kd was {{kd_mean_binder-1}}."))
    drafter = EmailDrafter(client=_FakeClient(fake_response))
    out = drafter.draft(_result(), findings=[])  # must not raise
    assert "1.20e-09" in out.body


def test_drafter_does_not_misread_a_hyphenated_label_as_a_negative_number():
    # Regression guard for the number regex: "binder-1" must NOT be parsed as
    # the number "-1". A naive `-?\d+` would match the hyphen in a
    # hyphenated sequence label as a negative sign, and "-1" is never in any
    # fact sheet or evidence text -- a naive regex would incorrectly raise
    # UngroundedNumberError on this completely benign, real sentence.
    fake_response = _FakeParseResponse(EmailDraftSchema(
        subject="s", body="Binder-1 showed strong binding with Kd {{kd_mean_binder-1}}."))
    drafter = EmailDrafter(client=_FakeClient(fake_response))
    out = drafter.draft(_result(), findings=[])  # must not raise
    assert "Binder-1" in out.body


def test_substitute_facts_raises_on_empty_placeholder():
    with pytest.raises(UnresolvedPlaceholderError):
        substitute_facts("Kd was {{}}.", {"kd_mean_binder-1": "1.20e-09 M"})


def test_substitute_facts_raises_on_multiline_placeholder():
    with pytest.raises(UnresolvedPlaceholderError):
        substitute_facts("Kd was {{bad\ntoken}}.", {"kd_mean_binder-1": "1.20e-09 M"})
```

Add to `tests/test_guards.py`:

```python
def test_guard_no_leftover_placeholder_syntax_catches_empty_and_multiline_constructs():
    # guard_no_leftover_placeholder_syntax is already imported at the top of this file.
    assert guard_no_leftover_placeholder_syntax("Kd was {{}}.")
    assert guard_no_leftover_placeholder_syntax("Kd was {{bad\ntoken}}.")


def test_all_numbers_grounded_accepts_findings_and_allows_evidence_numbers():
    # AnomalyFinding is already imported at the top of this file.
    finding = AnomalyFinding(rule="missing_replicates", severity="warning",
                             evidence="binder-1 has 0 replicate(s), policy requires 2")
    violations = guard_all_numbers_grounded(
        "binder-1 has 0 replicate(s), policy requires 2", {}, [finding])
    assert violations == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_email_drafter.py tests/test_guards.py -v -k "raw_number or evidence or empty_placeholder or multiline or accepts_findings"`
Expected: FAIL on all of them — `UngroundedNumberError` doesn't exist yet; `substitute_facts` doesn't raise on empty/multiline; `guard_all_numbers_grounded` doesn't accept a third `findings` argument.

- [ ] **Step 3: Add `UngroundedNumberError` to `adaptyv/errors.py`**

Replace:
```python
class AgentError(AdaptyvError): ...
class UnresolvedPlaceholderError(AgentError): ...
```
with:
```python
class AgentError(AdaptyvError): ...
class UnresolvedPlaceholderError(AgentError): ...
class UngroundedNumberError(AgentError): ...
```

- [ ] **Step 4: Fix `adaptyv/agents/email.py`**

Replace line 17-18:
```python
_PLACEHOLDER = re.compile(r"\{\{(.*?)\}\}", re.DOTALL)
_VALID_FACT_ID = re.compile(r"^[\w-]+$")
_NUMBER = re.compile(r"(?<![\w-])-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?%?")
# The `(?<![\w-])` negative lookbehind is required, not decorative: without
# it, `-?` greedily treats the hyphen in a hyphenated label like "binder-1"
# as a negative sign, extracting the spurious "number" -1 -- which is never
# grounded (no fact or evidence ever produces "-1"), so a naive regex here
# would raise UngroundedNumberError on the completely benign, real sentence
# "Binder-1 showed strong binding...". The lookbehind requires the
# character immediately before a candidate match to be neither a word
# character nor a hyphen, so "binder-1" and "seq1" are correctly seen as
# identifiers, not numbers -- verified empirically before this plan was
# written; see test_drafter_does_not_misread_a_hyphenated_label_as_a_negative_number.
```

Add these two functions immediately after `substitute_facts` (after line 60 in the current file):

```python
def grounded_numbers(fact_sheet: dict[str, str], findings: list[AnomalyFinding]) -> set[str]:
    """Every number a drafted email is allowed to contain: fact-sheet values
    (the only measurements the model may cite) and numbers appearing
    verbatim in anomaly evidence (the only other grounded-truth text passed
    into the prompt, which the drafter is instructed to echo directly).
    Anything else is fabrication."""
    grounded: set[str] = set()
    for value in fact_sheet.values():
        grounded.update(_NUMBER.findall(value))
    for f in findings:
        grounded.update(_NUMBER.findall(f.evidence))
    return grounded


def find_ungrounded_numbers(text: str, grounded: set[str]) -> list[str]:
    return [n for n in _NUMBER.findall(text) if n not in grounded]
```

Update the import line (line 7) to add the new error type:
```python
from adaptyv.errors import UngroundedNumberError, UnresolvedPlaceholderError
```

Replace `EmailDrafter.draft()`'s tail (the lines after `draft = response.parsed_output`):

```python
        draft = response.parsed_output
        resolved_subject = substitute_facts(draft.subject, fact_sheet)
        resolved_body = substitute_facts(draft.body, fact_sheet)
        grounded = grounded_numbers(fact_sheet, findings)
        for text in (resolved_subject, resolved_body):
            ungrounded = find_ungrounded_numbers(text, grounded)
            if ungrounded:
                raise UngroundedNumberError(
                    f"drafter emitted ungrounded number(s) {ungrounded} not traceable to any fact or anomaly evidence")
        return EmailDraftSchema(subject=resolved_subject, body=resolved_body)
```

- [ ] **Step 5: Fix `evals/guards.py`**

Replace line 9 (`_PLACEHOLDER = ...`):
```python
_PLACEHOLDER = re.compile(r"\{\{(.*?)\}\}", re.DOTALL)
```

Delete the `_SCI_NUMBER` line entirely (line 10 — no longer used, replaced by the shared `email.py` functions).

Replace `guard_all_numbers_grounded`:
```python
def guard_all_numbers_grounded(body: str, fact_sheet: dict[str, str],
                               findings: list[AnomalyFinding] | None = None) -> list[str]:
    from adaptyv.agents.email import find_ungrounded_numbers, grounded_numbers
    grounded = grounded_numbers(fact_sheet, findings or [])
    ungrounded = find_ungrounded_numbers(body, grounded)
    return [f"number '{n}' in body does not trace to any fact_sheet value or anomaly evidence" for n in ungrounded]
```

- [ ] **Step 6: Update `evals/run_eval.py` to pass `findings` for full parity with production**

Replace this line inside `run_case()`:
```python
    violations += guard_all_numbers_grounded(draft_email.body, fact_sheet)
```
with:
```python
    violations += guard_all_numbers_grounded(draft_email.body, fact_sheet, findings)
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_email_drafter.py tests/test_guards.py -v`
Expected: PASS, every test in both files, including all pre-existing ones (in particular `test_all_numbers_grounded_rejects_substring_false_negative` — the new `_NUMBER` regex must still greedily consume the full 3-digit exponent in `"1.20e-091 M"` as one token, exactly like the old `_SCI_NUMBER` did, so that test's substring-false-negative check still holds. If it fails, check `_NUMBER`'s exponent group `(?:[eE][+-]?\d+)?` is greedy, not lazy).

- [ ] **Step 8: Run the full suite and the offline eval**

Run: `python3 -m pytest -q` — expect all passing.
Run: `make eval` — expect `3 cases, 0 violation(s)`, exit 0. (If this fails, check whether `evals/fake_llm.py`'s `DeterministicFakeClient` ever echoes a number in its templated body that isn't grounded — read the file if needed and adjust the template, not the guard, since the guard is now the more strictly correct one.)

- [ ] **Step 9: Commit**

```bash
git add adaptyv/errors.py adaptyv/agents/email.py evals/guards.py evals/run_eval.py tests/test_email_drafter.py tests/test_guards.py
git commit -m "fix: production-time number-grounding guard; close empty/multiline placeholder regex gaps

Raw numbers with no {{}} syntax at all previously bypassed substitute_facts
entirely (it only ever touches text inside placeholder spans). Added
grounded_numbers()/find_ungrounded_numbers() in email.py, shared by both
EmailDrafter.draft() (raises UngroundedNumberError) and the offline
guard_all_numbers_grounded (now delegates instead of maintaining its own
separate regex -- closes the 'shared blind spot drifts out of sync'
pattern this project has hit twice before). Also widened the placeholder
regex to re.DOTALL + .*? so empty {{}} and multiline malformed constructs
are caught instead of silently passing through."
```

---

### Task 3: Rename `on_commit` to `before_commit`; enforce the same-connection precondition

**Files:**
- Modify: `adaptyv/governance/approval.py` (rename parameter; add `shares_connection_with`)
- Modify: `adaptyv/agents/watcher.py` (rename call site; add constructor assertion)
- Modify: `tests/test_approval_store.py`, `tests/test_watcher.py`

**Context:** The previous bugfix cycle added an `on_commit` hook to `ApprovalStore.create_draft()` so `Watcher` could write its idempotency marker atomically with the draft+audit write. Two issues found on review: (1) the name `on_commit` is misleading — the hook actually runs BEFORE the commit (it has to, for atomicity to work — `AuditLog.record()` is the actual commit point), not after; (2) the atomicity guarantee silently depends on `Watcher` and its `ApprovalStore` sharing the exact same sqlite connection object, but `Watcher.__init__` accepts `approval_store` and `conn` as independent parameters with no check that they're consistent — a future caller passing a different connection to each would silently break atomicity with no error.

**Interfaces:**
- Produces: `ApprovalStore.create_draft(..., before_commit: Callable[[str], None] | None = None) -> Draft` — same behavior as the old `on_commit`, renamed.
- Produces: `ApprovalStore.shares_connection_with(conn: sqlite3.Connection) -> bool` — `True` iff this store's connection is the exact same object as `conn`.
- Consumes (by Watcher): `Watcher.__init__` now raises `ValueError` if `not approval_store.shares_connection_with(conn)`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_approval_store.py` (rename the existing two `on_commit` tests too — read the file first to find their exact current names and update both the parameter name in the call and the test names):

Rename `test_create_draft_on_commit_hook_runs_in_the_same_transaction` to `test_create_draft_before_commit_hook_runs_in_the_same_transaction`, changing its `on_commit=` kwarg to `before_commit=`.
Rename `test_create_draft_on_commit_failure_rolls_back_the_draft_too` to `test_create_draft_before_commit_failure_rolls_back_the_draft_too`, changing its `on_commit=` kwarg to `before_commit=`.

Add a new test:
```python
def test_shares_connection_with_identifies_the_same_connection_object():
    conn = connect()
    other_conn = connect()
    store = ApprovalStore(conn, AuditLog(conn))
    assert store.shares_connection_with(conn) is True
    assert store.shares_connection_with(other_conn) is False
```

Add to `tests/test_watcher.py`:
```python
def test_watcher_rejects_a_store_using_a_different_connection():
    conn = connect()
    other_conn = connect()
    store = ApprovalStore(conn, AuditLog(conn))  # store uses `conn`
    with pytest.raises(ValueError):
        Watcher(AdaptyvClient(mock=True), AnomalyDetector(DEFAULT_POLICY), _FakeDrafter(),
               store, other_conn)  # but Watcher is given `other_conn` -- mismatch
```
(Add `import pytest` to the top of `tests/test_watcher.py` if not already imported — check first.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_approval_store.py tests/test_watcher.py -v -k "before_commit or shares_connection or rejects_a_store"`
Expected: FAIL — `create_draft()` doesn't accept `before_commit` yet (`TypeError`); `shares_connection_with` doesn't exist yet (`AttributeError`); `Watcher.__init__` doesn't raise on a connection mismatch yet.

- [ ] **Step 3: Rename `on_commit` to `before_commit` and add `shares_connection_with` in `adaptyv/governance/approval.py`**

In `create_draft`, rename the parameter `on_commit` to `before_commit` everywhere it appears (the signature, the `if on_commit is not None: on_commit(draft_id)` line becomes `if before_commit is not None: before_commit(draft_id)`).

Add this method anywhere among the other public methods (e.g. right after `create_draft`):
```python
    def shares_connection_with(self, conn: sqlite3.Connection) -> bool:
        return self._conn is conn
```

- [ ] **Step 4: Update `adaptyv/agents/watcher.py`**

In `Watcher.__init__`, add a check before the existing body (right after the parameter list, before the `self._client = client` line):
```python
    def __init__(self, client, detector: AnomalyDetector, drafter: EmailDrafter,
                approval_store: ApprovalStore, conn: sqlite3.Connection) -> None:
        if not approval_store.shares_connection_with(conn):
            raise ValueError(
                "Watcher's conn must be the exact same connection object as approval_store's "
                "-- the atomic before_commit hook can only be atomic if both write through one connection")
        self._client = client
        ...
```
(Keep the rest of `__init__` exactly as it is — just add the check as the first statement in the method body.)

In `run()`, rename the `on_commit=` kwarg passed to `create_draft` to `before_commit=`:
```python
                    draft = self._store.create_draft(
                        experiment_id, body, result_id=result.id, anomalies=findings,
                        created_by=Actor(kind="agent", id="watcher"),
                        before_commit=lambda draft_id, key=key: self._conn.execute(
                            "INSERT INTO watcher_processed (key, draft_id) VALUES (?, ?)",
                            (key, draft_id)))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_approval_store.py tests/test_watcher.py -v`
Expected: PASS, every test in both files.

- [ ] **Step 6: Run the full suite**

Run: `python3 -m pytest -q`
Expected: all passing.

- [ ] **Step 7: Commit**

```bash
git add adaptyv/governance/approval.py adaptyv/agents/watcher.py tests/test_approval_store.py tests/test_watcher.py
git commit -m "fix: rename on_commit to before_commit; enforce Watcher/ApprovalStore share one connection

The hook runs before the transaction commits (it has to, for atomicity),
so on_commit was a misleading name. Also, the atomicity guarantee silently
depended on Watcher and its ApprovalStore using the exact same sqlite
connection, with no check -- a future caller passing mismatched
connections would silently lose atomicity. Watcher's constructor now
rejects that combination outright."
```
