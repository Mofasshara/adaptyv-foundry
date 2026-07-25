# Adaptyv Foundry SDK + MCP + Lab Ops Agent — Project Roadmap

> **Goal:** Wrap the Adaptyv Foundry lab API in a clean typed Python SDK, expose it to Claude via a TypeScript MCP server, and build a governed ExperimentWatcher agent that drafts customer result emails with human sign-off, an audit trail, and feedback loops.
> **Started:** 2026-07-24
> **Constraints:** Take-home scope (demoable in a 2-min Loom); Python SDK + TypeScript MCP are hard requirements; no live API key (mock mode mandatory); solo build; code quality/type-safety/clean README are the primary review criteria.
> **Scope strategy:** **Core solid first**, differentiators as labeled **stretch**. Core = faithful SDK + MCP + one excellent watcher path + HITL + deterministic evals. Stretch = hash-chained audit, 3 feedback loops, live LLM-judge, TestPyPI publish.

---

## Status Overview

| Status       | Count |
|--------------|-------|
| ✅ Done       | 32    |
| 🔄 In Progress | 0   |
| ⏳ Pending    | 1     |
| 🚫 Blocked    | 0     |

**Total estimated time:** ≈46h (~5.75d) — of which ≈13h is labeled stretch
**Elapsed time:** ≈15h10m
**Remaining estimate:** ≈7h15m

---

## Stack & Tools

| Tool / Technology | Purpose | Introduced In |
|-------------------|---------|---------------|
| Python 3.11+ (venv) | SDK, agent, bridge language | Phase 1 |
| pydantic v2 | Typed models mirroring the OpenAPI schemas (incl. discriminated unions, pagination) | Phase 1 |
| httpx | Sync HTTP client for LiveTransport | Phase 1 |
| Typer | Human-facing CLI (`adaptyv ...`) | Phase 1 |
| pytest + respx | Testing; httpx mocking | Phase 1 |
| jsonschema | Contract test: fixtures validated against pinned OpenAPI schema | Phase 1 |
| SQLite | Append-only audit + feedback store (hash-chaining is stretch) | Phase 2 |
| Anthropic SDK (Claude) | Email drafting + LLM-as-judge | Phase 3 / 5 |
| TypeScript + @modelcontextprotocol/sdk | MCP server for Claude Desktop/Code | Phase 4 |
| Subprocess JSON bridge (`python -m adaptyv --json`) | MCP→SDK delegation (replaces FastAPI sidecar) | Phase 4 |
| Zod | MCP tool parameter schemas + descriptions | Phase 4 |
| hatchling + TestPyPI | Packaging & (test) distribution — **stretch** | Phase 6 |

---

## Phases

### Phase 1 — SDK Core  ✅

**Goal:** Typed, sync Python SDK faithful to the real API, with mock mode and read+write coverage — `AdaptyvClient(mock=True)` returns typed lab data with no key; mock/live shapes identical. (Plan: `docs/superpowers/plans/2026-07-24-phase1-sdk-core.md`, v2 schema-corrected)
**Phase estimate:** ~11h

| # | Task | Status | Estimate | Started | Completed | Notes |
|---|------|--------|----------|---------|-----------|-------|
| 1 | Scaffold package (venv, pyproject) + vendor pinned OpenAPI spec | ✅ Done | 45m | 2026-07-24 10:40 | 2026-07-24 10:50 | core |
| 2 | Schema-faithful pydantic models (enums, discriminated results, pagination, list-vs-detail) | ✅ Done | 2h | 2026-07-24 10:55 | 2026-07-24 11:05 | core; derived from raw spec |
| 3 | Transport, errors, pagination-aware MockTransport + fixtures + OpenAPI contract test | ✅ Done | 2h30m | 2026-07-24 11:08 | 2026-07-24 11:18 | core |
| 4 | AdaptyvClient + paginated experiments resource | ✅ Done | 1h | 2026-07-24 11:20 | 2026-07-24 11:25 | core |
| 5 | Experiment write methods (create/submit/cost_estimate) | ✅ Done | 1h30m | 2026-07-24 11:28 | 2026-07-24 11:35 | core; needed by MCP |
| 6 | sequences, targets, results resources (incl. sequences.add) | ✅ Done | 1h30m | 2026-07-24 11:38 | 2026-07-24 11:50 | core |
| 7 | LiveTransport (idempotent-only retry, Retry-After, real error body) | ✅ Done | 1h30m | 2026-07-24 11:52 | 2026-07-24 12:02 | core |
| 8 | Minimal Typer CLI + final review & fix wave | ✅ Done | 45m | 2026-07-24 12:04 | 2026-07-24 12:30 | core; 44/44 tests green |

### Phase 2 — Governance Layer  ✅

**Goal:** Human-in-the-loop approval state machine + audit trail the agent and MCP write through. (Plan: `docs/superpowers/plans/2026-07-24-phase2-governance.md`)
**Phase estimate:** ~6h45m (~1h of it stretch)

| # | Task | Status | Estimate | Started | Completed | Notes |
|---|------|--------|----------|---------|-----------|-------|
| 0 | Governance domain models + errors + sqlite helper | ✅ Done | 45m | 2026-07-24 19:04 | 2026-07-24 19:06 | core |
| 1 | Append-only, **hash-chained** SQLite audit log + `verify()` | ✅ Done | 1h30m | 2026-07-24 19:08 | 2026-07-24 19:10 | core (chain moved from #4) |
| 2 | Draft approval state machine (PendingReview→Approved/Rejected/Sent); agent cannot self-approve | ✅ Done | 1h30m | 2026-07-24 19:12 | 2026-07-24 19:14 | core |
| 3 | Critical-anomaly hard-block + human acknowledgement | ✅ Done | 1h | 2026-07-24 19:16 | 2026-07-24 19:17 | core |
| 4 | `adaptyv review` + `adaptyv audit` CLI over the governance store | ✅ Done | 1h | 2026-07-24 19:19 | 2026-07-24 19:21 | core |
| 5 | Feedback store for corrected drafts (flywheel source) | ✅ Done | 1h | 2026-07-24 19:23 | 2026-07-24 19:24 | **stretch**; built |
| 6 | Final review + 2 fix waves (atomic state+audit commit, tail-truncation detect, CLI error handling) | ✅ Done | 45m | 2026-07-24 19:25 | 2026-07-24 19:35 | core; 71/71 tests green |

### Phase 3 — ExperimentWatcher Agent  ✅

**Goal:** Given completed results, produce a plain-English customer-update draft (PendingReview) + structured anomaly report; numbers substituted from data via typed placeholders. (Plan: `docs/superpowers/plans/2026-07-24-phase3-experimentwatcher.md`)
**Phase estimate:** ~7h45m

| # | Task | Status | Estimate | Started | Completed | Notes |
|---|------|--------|----------|---------|-----------|-------|
| 1 | Define versioned anomaly policy (thresholds, control identity, units, missing-data semantics) | ✅ Done | 1h | 2026-07-24 23:16 | 2026-07-24 23:18 | core; policy is an input, not hardcoded |
| 2 | Deterministic AnomalyDetector + tests | ✅ Done | 2h | 2026-07-24 23:20 | 2026-07-24 23:24 | core; vacuous-truth guard verified |
| 3 | Add anomalous affinity fixtures (all-failed, control-out-of-policy) | ✅ Done | 45m | 2026-07-24 23:26 | 2026-07-24 23:30 | core; full-suite regression-checked |
| 4 | EmailDrafter (Claude; typed placeholder → validated numeric substitution) | ✅ Done | 2h | 2026-07-24 23:32 | 2026-07-24 23:45 | core; claude-opus-4-8 via claude-api skill |
| 5 | Watcher orchestration with durable idempotency key (experiment_id, result_id, version) + final review & fix wave | ✅ Done | 1h45m | 2026-07-24 23:47 | 2026-07-25 09:15 | core; 99/99 tests green |

### Phase 4 — MCP Server (via subprocess bridge)  ✅

**Goal:** One-command MCP server in Claude Desktop driving the lab via ~8 curated task-shaped tools, delegating to the Python SDK through a subprocess JSON bridge.
**Phase estimate:** ~7h

| # | Task | Status | Estimate | Started | Completed | Notes |
|---|------|--------|----------|---------|-----------|-------|
| 1 | `python -m adaptyv --json <op>` bridge command (stdin/stdout JSON, typed errors) | ✅ Done | 1h30m | 2026-07-25 00:30 | 2026-07-25 00:36 | core; replaces FastAPI sidecar |
| 2 | Scaffold TS MCP server + bridge client (spawn per call) | ✅ Done | 1h30m | 2026-07-25 00:36 | 2026-07-25 00:42 | core |
| 3 | ~8 task-shaped tools with Zod descriptions | ✅ Done | 3h | 2026-07-25 00:42 | 2026-07-25 00:50 | core; not 1:1 CRUD |
| 4 | MCP tool tests against a stubbed bridge + composition root (`index.ts`) wiring all 8 tools into a runnable server | ✅ Done | 1h | 2026-07-25 00:52 | 2026-07-25 00:59 | core; also fixed a real bug: relative `pythonPath` is unsafe when an MCP client spawns the server from an arbitrary cwd — `index.ts` now resolves an absolute path via `import.meta.url`, reproduced and verified fixed with a live cross-cwd bridge call |

### Phase 5 — Evals + Loops  ✅

**Goal:** Trustworthy output — deterministic guards (core) + LLM-judge and feedback loops (stretch).
**Phase estimate:** ~8h (~5h of it stretch)

| # | Task | Status | Estimate | Started | Completed | Notes |
|---|------|--------|----------|---------|-----------|-------|
| 1 | Golden set (results → expected typed facts) | ✅ Done | 1h | 2026-07-25 01:05 | 2026-07-25 01:20 | core; 3 real-fixture-anchored cases |
| 2 | Deterministic guards (exact fact-id substitution, anomalies caught) | ✅ Done | 1h30m | 2026-07-25 01:22 | 2026-07-25 01:45 | core; fix wave: approval-guard idempotency + exact-token number grounding |
| 3 | Eval→improve loop (`make eval` report) | ✅ Done | 1h | 2026-07-25 01:47 | 2026-07-25 02:05 | core; fix wave: added missing FAIL/exit-1 path test coverage |
| 4 | LLM-judge rubric (accuracy/completeness/tone) — reported as artifact, not CI gate | ⏳ Pending | 2h | — | — | **stretch — explicitly descoped for Phase 5** by user's choice ("Core + flywheel + watch loop"); requires live costed Anthropic API calls |
| 5 | Human-feedback flywheel (promote feedback-store corrections → golden set) | ✅ Done | 1h30m | 2026-07-25 02:07 | 2026-07-25 02:25 | stretch; built |
| 6 | Autonomous watch loop (interval, idempotent) | ✅ Done | 1h | 2026-07-25 02:27 | 2026-07-25 02:40 | stretch; fix wave: `Watcher.errors` now cleared each cycle so stale errors aren't reprinted forever; final whole-branch review clean, no fixes needed; 144/144 Python tests green, `make eval` 3/3 PASS |

### Phase 6 — Polish & Deliverables  🔄

**Goal:** Reviewer-ready repo: README, architecture diagram, learning guide, packaging, Loom script.
**Phase estimate:** ~6h (~1h of it stretch)

| # | Task | Status | Estimate | Started | Completed | Notes |
|---|------|--------|----------|---------|-----------|-------|
| 1 | README (value, quickstart, honest scope + limitations) | ✅ Done | 1h30m | 2026-07-26 12:38 | 2026-07-26 13:10 | core; every documented command verified working end-to-end before writing it — caught and fixed a real CLI bug (`review list` truncated draft_id to 8 chars, but `review show`/`approve` need an exact match) in the process |
| 2 | Architecture diagram + data-flow doc | ✅ Done | 1h | 2026-07-26 13:10 | 2026-07-26 13:25 | core; `docs/ARCHITECTURE.md` — system diagram, 8-tool table, 2 traced end-to-end flows, and a dedicated section on how hallucination-prevention actually works now |
| 3 | Finalize LEARNING_GUIDE | ✅ Done | 1h | 2026-07-26 13:25 | 2026-07-26 13:45 | core; was stale since pre-implementation (2026-07-24) — removed a fictional LLM-as-judge section that was never built, updated the placeholder-substitution entry to the final deny-by-default design, fixed the TestPyPI section's tense, added 2 new concept entries (deny-by-default vs. detection; idempotency) |
| 4 | Loom demo script | ✅ Done | 45m | 2026-07-26 13:45 | 2026-07-26 13:55 | core; `docs/LOOM_SCRIPT.md` — every command in it verified to actually run as written; recording itself is the user's step |
| 5 | TestPyPI packaging + install verification | ⏳ Pending | 1h | — | — | **stretch**; local editable install verified working (used throughout this build); actual publish needs the user's own PyPI account/token — asking before taking any external, visible action |

---

## Change Log

> The roadmap above reflects the current plan. This log records every deviation from the original design — it is permanent and append-only.

| Date | Change | Reason | Impact | Original Plan |
|------|--------|--------|--------|---------------|
| 2026-07-24 15:30 | Corrected the entire SDK data model against the raw OpenAPI spec | A Codex pre-implementation review + raw-JSON verification proved the v1 models/fixtures were built on a hallucinated WebFetch schema summary (wrong enums, missing pagination envelope, flattened result union) | Rewrote Phase 1 plan (models, transport, fixtures, contract test); added tests/data pinned spec + jsonschema contract test | v1 models with invented `ExperimentStatus` values, bare-array list responses, flat `ResultSummary` |
| 2026-07-24 15:32 | MCP→SDK mechanism changed from auto-spawned FastAPI sidecar to a subprocess JSON bridge (`python -m adaptyv --json`) | Codex flagged (and user agreed) that stdio-MCP auto-spawning a web server hides port/readiness/cleanup/version-skew complexity not worth it for a take-home | Phase 4 tasks re-specified around a per-call subprocess bridge; removed FastAPI from core stack | Phase 4 built a FastAPI sidecar auto-spawned by the MCP |
| 2026-07-24 15:34 | Re-sequenced to core-first; tagged hash-chain audit, 3 loops, live LLM-judge, TestPyPI as stretch; added SDK write methods to Phase 1 | Codex flagged ~41h scope risked leaving hard requirements shallow, and that Phase 1 lacked the write methods Phase 4's MCP needs | Phase 1 grew (+write tasks); Phases 2/5/6 items tagged core/stretch; total ≈46h with ~13h stretch | All 30 tasks equal priority; Phase 1 read-only |
| 2026-07-24 13:00 | Phase 2 audit **hash-chain + `verify()` moved from stretch into the core audit task**; only the feedback store stays stretch. Split Phase 2 into 6 finer plan tasks (models, audit, approval, anomaly-gate, CLI, feedback) | The chain is a few lines and an unverifiable chain has no demo/governance value; keeping them together avoids a schema migration | Phase 2 core now delivers a tamper-evident, verifiable log; feedback store remains the only Phase 2 stretch item | Hash-chain + verify were Phase 2 task #4 (stretch) |
| 2026-07-24 19:36 | Phase 2 final review found and fixed 2 integrity gaps: (1) draft state writes and their audit entry weren't committed atomically — a failed audit write could leave an unaudited state change; (2) `AuditLog.verify()` couldn't detect deletion of the newest entries (tail-truncation) | Whole-branch review reasoned through failure modes the per-task reviews (correctly) didn't check across components; a re-review of the first fix then caught a follow-on gap (no rollback-on-exception, so a failed write could be silently swept into a later commit) | `ApprovalStore` mutations now commit atomically with `AuditLog.record()` and roll back on failure; `AuditLog` gained `head()` + `verify(expected_head=...)` for tail-truncation detection; CLI `list` commands now use the shared error handler; added an honest tamper-evidence-not-tamper-proof docstring | Audit log described only as "hash-chained, append-only" with no atomicity/rollback or truncation-detection contract specified |
| 2026-07-25 02:41 | Phase 5 built as "Core + flywheel + watch loop"; the LLM-judge rubric task (Phase 5 #4) explicitly descoped for this phase | User's explicit scope choice — the LLM-judge requires live, costed Anthropic API calls, which is a call only the user should make, not something to default into during a take-home build | Phase 5 delivers golden set + deterministic guards + eval→improve loop + human-feedback flywheel + autonomous watch loop as the CI-gating eval suite; LLM-judge remains Pending, not blocking Phase 5's ✅ badge | All 6 Phase 5 tasks, including the LLM-judge, were originally equal-priority stretch/core items with no task explicitly deferred |
| 2026-07-25 09:00 | Unplanned bugfix cycle: a second external (Codex) whole-project review run against the merged main branch (post-Phase-5) found 3 BLOCKING defects; user chose "BLOCKING only" scope. Fixed on branch `bugfix-codex-blocking-findings`, merged to main: (1) `ExperimentSpec.sequences` corrected from a JSON array to the real OpenAPI's name-keyed object, `method`/`n_replicates` exposed end-to-end through the MCP tools; (2) `EmailDrafter.draft()` now validates the email subject through `substitute_facts()`, not just the body, and the shared placeholder regex (production + eval guard) widened to catch malformed constructs it previously let through silently; (3) `Watcher`'s `watcher_processed` idempotency marker now commits atomically with the draft+audit write via a new `on_commit` hook on `ApprovalStore.create_draft()`, closing both a duplicate-draft-on-crash bug and a 4th instance of the "one bad item crashes the whole batch" pattern this project has hit repeatedly | 10 SHOULD-FIX and 2 NICE-TO-HAVE findings from the same review (bridge non-dict-JSON crash, MCP `db`/`mock_llm` exposure, cross-connection concurrency races, flywheel data loss, pagination-limit semantics, live-transport network-error mapping, MCP bridge-client timeout/validation hardening, etc.) were deliberately NOT fixed — logged here as known follow-ups, not silently dropped | No roadmap task changed status (this was corrective work on already-"done" phases, not new scope); 156/156 Python + 16/16 TypeScript tests green post-merge, `make eval` still 3/3 PASS | Phases 1-5 were marked ✅ Done on the assumption their final whole-branch reviews were exhaustive; this review found real gaps a second, independent pass surfaced that the original per-phase reviews did not |
| 2026-07-26 10:30 | Second unplanned bugfix cycle: user asked for a Codex re-review verifying the previous bugfix cycle's 3 fixes. It found a genuine NEW regression in fix #1 (`_sequences_by_name` silently dropped a sequence on a name collision) plus two incompleteness gaps (raw un-braced numbers still bypassed the email guard entirely; the `on_commit` hook name was misleading and its same-connection precondition was unenforced). User chose "fix everything Codex flagged" this time. Fixed on branch `bugfix-codex-review-round2`, merged to main: (1) `_sequences_by_name` now raises `BridgeError` on any name collision instead of silently overwriting; (2) added a genuinely new production-time `grounded_numbers()`/`find_ungrounded_numbers()` check in `EmailDrafter.draft()` that catches raw numbers with no `{{}}` syntax at all, raising a new `UngroundedNumberError`, with the offline eval guard now delegating to the same shared functions instead of maintaining a separate regex; (3) `on_commit` renamed to `before_commit`, plus a new `ApprovalStore.shares_connection_with()` + a `Watcher.__init__` assertion that rejects a mismatched connection | Full re-verification of a previous fix is worth doing before treating "reviewed once" as "done" — this cycle proved that even a reviewed, tested, merged fix (round 1) can itself introduce a new regression, and that "BLOCKING only" scoping in round 1 had silently left the underlying hallucination-prevention guarantee only partially closed | No roadmap task changed status (corrective work on an already-merged bugfix, not new scope); 170/170 Python + 16/16 TypeScript tests green post-merge, `make eval` still 3/3 PASS | The round-1 Change Log entry above described those 3 fixes as complete; this entry corrects that record — fix #1 needed a genuine regression fix, fixes #2 and #3 needed to be extended beyond what round 1 shipped |
| 2026-07-26 12:38 | Third bugfix cycle, done directly (no subagent-dispatch/review-loop ceremony) at the user's explicit request to stop the round-and-round review cycle and fix root causes fast. A "final" Codex review still found the email hallucination guard fundamentally broken (accepted a raw, un-placeholder'd number whenever it coincided with a real fact value — Codex's exact repro: "Kd was 1.20e-09 M" typed as plain prose, accepted because 1.20e-09 happened to be a real fact), plus two independent findings (mock write responses for cost-estimate/submit didn't match the real OpenAPI response schemas at all; mock/MCP experiment creation accepted requests — e.g. affinity with no method/target_id — that the live API would reject). Root-cause fix, not another patch: replaced the entire "check if a number is in a grounded set" design with deny-by-default — `substitute_facts()` now rejects any digit outside a `{{...}}` span in the raw model output before substitution even starts, and rejects any leftover `{`/`}` character afterward (one generic check replacing several enumerated regex edge-cases). Anomaly-evidence numbers are now templated into their own placeholders before the prompt is built, so the model's instructed "echo evidence verbatim" behavior can no longer reintroduce a raw number. Fact-sheet keys became an opaque counter (`kd_1`, `kd_2`, ...) instead of name-derived, eliminating the collision-disambiguation logic entirely. The now-redundant offline eval guards (`guard_no_leftover_placeholder_syntax`, `guard_all_numbers_grounded`) were deleted outright — they duplicated a guarantee that now lives once, correctly, in production code, and having two implementations of the same check is exactly how this bug survived three review rounds. Also added `CostBreakdown`/`AssayCost`/`ExperimentConfirmationResponse` models and fixed `MockTransport`'s cost-estimate/submit responses to match the real schemas; added a pydantic model validator on `ExperimentSpec` enforcing the OpenAPI assay matrix (method/target_id required-or-rejected per experiment type, ≥1 sequence, epitope_binning's count/replicate constraints) | User was explicit that going through another full plan-write/subagent-dispatch/multi-round-review cycle for a 4th time was unacceptable, and asked for the underlying pattern (why do fixes keep needing re-fixing) to be addressed, not just the latest symptom | No roadmap task changed status; 170/170 Python + 16/16 TypeScript tests green post-merge, `make eval` 3/3 PASS; the SHOULD-FIX/NICE-TO-HAVE items from this and prior reviews (stale-result idempotency key doesn't include a result-version/policy-version component, `draft_customer_update` can return a stale historical draft without checking current-run errors, audit trail doesn't record a full lineage manifest, and the items logged in the two entries above) remain open and are NOT re-litigated here | The two entries above each described their fixes as closing the hallucination-prevention gap; both were wrong, because both treated the guard as a detection problem (enumerate bad patterns and reject them) instead of a construction problem (deny everything by default, allow only through a verified mechanism) |
