# Adaptyv Foundry SDK + MCP + Lab Ops Agent — Project Roadmap

> **Goal:** Wrap the Adaptyv Foundry lab API in a clean typed Python SDK, expose it to Claude via a TypeScript MCP server, and build a governed ExperimentWatcher agent that drafts customer result emails with human sign-off, an audit trail, and feedback loops.
> **Started:** 2026-07-24
> **Constraints:** Take-home scope (demoable in a 2-min Loom); Python SDK + TypeScript MCP are hard requirements; no live API key (mock mode mandatory); solo build; code quality/type-safety/clean README are the primary review criteria.
> **Scope strategy:** **Core solid first**, differentiators as labeled **stretch**. Core = faithful SDK + MCP + one excellent watcher path + HITL + deterministic evals. Stretch = hash-chained audit, 3 feedback loops, live LLM-judge, TestPyPI publish.

---

## Status Overview

| Status       | Count |
|--------------|-------|
| ✅ Done       | 14    |
| 🔄 In Progress | 0   |
| ⏳ Pending    | 19    |
| 🚫 Blocked    | 0     |

**Total estimated time:** ≈46h (~5.75d) — of which ≈13h is labeled stretch
**Elapsed time:** ≈1h
**Remaining estimate:** ≈45h (~5.625d)

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

### Phase 3 — ExperimentWatcher Agent  ⏳

**Goal:** Given completed results, produce a plain-English customer-update draft (PendingReview) + structured anomaly report; numbers substituted from data via typed placeholders.
**Phase estimate:** ~7h

| # | Task | Status | Estimate | Started | Completed | Notes |
|---|------|--------|----------|---------|-----------|-------|
| 1 | Define versioned anomaly policy (thresholds, control identity, units, missing-data semantics) | ⏳ Pending | 1h | — | — | core; policy is an input, not hardcoded |
| 2 | Deterministic AnomalyDetector + tests | ⏳ Pending | 2h | — | — | core |
| 3 | Add anomalous affinity fixtures (all-failed, control-out-of-policy) | ⏳ Pending | 45m | — | — | core |
| 4 | EmailDrafter (Claude; typed placeholder → validated numeric substitution) | ⏳ Pending | 2h | — | — | core; model IDs via claude-api skill |
| 5 | Watcher orchestration with durable idempotency key (experiment_id, result_id, version) | ⏳ Pending | 1h30m | — | — | core |

### Phase 4 — MCP Server (via subprocess bridge)  ⏳

**Goal:** One-command MCP server in Claude Desktop driving the lab via ~8 curated task-shaped tools, delegating to the Python SDK through a subprocess JSON bridge.
**Phase estimate:** ~7h

| # | Task | Status | Estimate | Started | Completed | Notes |
|---|------|--------|----------|---------|-----------|-------|
| 1 | `python -m adaptyv --json <op>` bridge command (stdin/stdout JSON, typed errors) | ⏳ Pending | 1h30m | — | — | core; replaces FastAPI sidecar |
| 2 | Scaffold TS MCP server + bridge client (spawn per call) | ⏳ Pending | 1h30m | — | — | core |
| 3 | ~8 task-shaped tools with Zod descriptions | ⏳ Pending | 3h | — | — | core; not 1:1 CRUD |
| 4 | MCP tool tests against a stubbed bridge | ⏳ Pending | 1h | — | — | core |

### Phase 5 — Evals + Loops  ⏳

**Goal:** Trustworthy output — deterministic guards (core) + LLM-judge and feedback loops (stretch).
**Phase estimate:** ~8h (~5h of it stretch)

| # | Task | Status | Estimate | Started | Completed | Notes |
|---|------|--------|----------|---------|-----------|-------|
| 1 | Golden set (results → expected typed facts) | ⏳ Pending | 1h | — | — | core |
| 2 | Deterministic guards (exact fact-id substitution, anomalies caught) | ⏳ Pending | 1h30m | — | — | core |
| 3 | Eval→improve loop (`make eval` report) | ⏳ Pending | 1h | — | — | core |
| 4 | LLM-judge rubric (accuracy/completeness/tone) — reported as artifact, not CI gate | ⏳ Pending | 2h | — | — | **stretch** |
| 5 | Human-feedback flywheel (promote feedback-store corrections → golden set) | ⏳ Pending | 1h30m | — | — | **stretch** |
| 6 | Autonomous watch loop (interval, idempotent) | ⏳ Pending | 1h | — | — | **stretch** |

### Phase 6 — Polish & Deliverables  ⏳

**Goal:** Reviewer-ready repo: README, architecture diagram, learning guide, packaging, Loom script.
**Phase estimate:** ~6h (~1h of it stretch)

| # | Task | Status | Estimate | Started | Completed | Notes |
|---|------|--------|----------|---------|-----------|-------|
| 1 | README (value, quickstart, honest scope + limitations) | ⏳ Pending | 1h30m | — | — | core |
| 2 | Architecture diagram + data-flow doc | ⏳ Pending | 1h | — | — | core |
| 3 | Finalize LEARNING_GUIDE | ⏳ Pending | 1h | — | — | core |
| 4 | Loom demo script | ⏳ Pending | 45m | — | — | core; user records |
| 5 | TestPyPI packaging + install verification | ⏳ Pending | 1h | — | — | **stretch** |

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
