# Adaptyv Foundry SDK + MCP + Lab Ops Agent — Project Roadmap

> **Goal:** Wrap the Adaptyv Foundry lab API in a clean typed Python SDK, expose it to Claude via a TypeScript MCP server, and build a governed ExperimentWatcher agent that drafts customer result emails with human sign-off, a tamper-evident audit trail, and feedback loops.
> **Started:** 2026-07-24
> **Constraints:** Take-home scope (demoable in a 2-min Loom); Python SDK + TypeScript MCP are hard requirements; no live API key (mock mode mandatory); solo build; code quality/type-safety/clean README are the primary review criteria.

---

## Status Overview

| Status       | Count |
|--------------|-------|
| ✅ Done       | 0     |
| 🔄 In Progress | 0   |
| ⏳ Pending    | 30    |
| 🚫 Blocked    | 0     |

**Total estimated time:** ≈41h (~5d)
**Elapsed time:** —
**Remaining estimate:** ≈41h (~5d)

---

## Stack & Tools

| Tool / Technology | Purpose | Introduced In |
|-------------------|---------|---------------|
| Python 3.11+ | SDK, agent, sidecar language | Phase 1 |
| pydantic v2 | Typed models mirroring the OpenAPI schemas | Phase 1 |
| httpx | Sync HTTP client for LiveTransport | Phase 1 |
| Typer | Human-facing CLI (`adaptyv ...`) | Phase 1 |
| pytest + respx | Testing; httpx mocking | Phase 1 |
| SQLite | Hash-chained append-only audit store | Phase 2 |
| Anthropic SDK (Claude) | Email drafting + LLM-as-judge | Phase 3 / 5 |
| FastAPI | Local sidecar exposing the SDK to the MCP | Phase 4 |
| TypeScript + @modelcontextprotocol/sdk | MCP server for Claude Desktop/Code | Phase 4 |
| Zod | MCP tool parameter schemas + descriptions | Phase 4 |
| hatchling + TestPyPI | Packaging & (test) distribution | Phase 6 |

---

## Phases

### Phase 1 — SDK Core  ⏳

**Goal:** Typed, sync Python SDK with mock mode — `AdaptyvClient(mock=True)` returns typed lab data with no API key. (Detailed plan: `docs/superpowers/plans/2026-07-24-phase1-sdk-core.md`)
**Phase estimate:** ~7.5h

| # | Task | Status | Estimate | Started | Completed | Notes |
|---|------|--------|----------|---------|-----------|-------|
| 1 | Scaffold SDK package (pyproject, layout, pytest) | ⏳ Pending | 30m | — | — | |
| 2 | Implement pydantic models + enums | ⏳ Pending | 1h | — | — | Fields grounded in real OpenAPI spec |
| 3 | Implement transport protocol, errors, MockTransport + fixtures + contract test | ⏳ Pending | 2h | — | — | Contract test binds fixtures to models |
| 4 | Implement AdaptyvClient + experiments resource | ⏳ Pending | 1h | — | — | |
| 5 | Implement sequences, targets, results resources | ⏳ Pending | 1h | — | — | |
| 6 | Implement LiveTransport (httpx) + retry + error mapping | ⏳ Pending | 1h30m | — | — | |
| 7 | Implement minimal Typer CLI | ⏳ Pending | 45m | — | — | |

### Phase 2 — Governance Layer  ⏳

**Goal:** Tamper-evident audit trail and human-in-the-loop approval state machine that the agent and MCP write through.
**Phase estimate:** ~6h

| # | Task | Status | Estimate | Started | Completed | Notes |
|---|------|--------|----------|---------|-----------|-------|
| 1 | Implement hash-chained append-only SQLite audit log + `verify` | ⏳ Pending | 2h | — | — | |
| 2 | Implement draft approval state machine (Draft→PendingReview→Approved/Rejected) | ⏳ Pending | 1h30m | — | — | Agent cannot self-approve |
| 3 | Implement critical-anomaly hard-block + human acknowledgement | ⏳ Pending | 1h | — | — | |
| 4 | Wire audit + data lineage into state-changing operations | ⏳ Pending | 1h30m | — | — | |

### Phase 3 — ExperimentWatcher Agent  ⏳

**Goal:** Given completed results, produce a plain-English customer-update draft (PendingReview) + structured anomaly report; numbers injected from data, never invented.
**Phase estimate:** ~6.25h

| # | Task | Status | Estimate | Started | Completed | Notes |
|---|------|--------|----------|---------|-----------|-------|
| 1 | Implement deterministic AnomalyDetector rules + tests | ⏳ Pending | 2h | — | — | all-failed, control-out-of-range = critical |
| 2 | Add anomalous fixtures (all-failed, control-out-of-range) | ⏳ Pending | 45m | — | — | |
| 3 | Implement EmailDrafter (Claude; facts injected) | ⏳ Pending | 2h | — | — | Model IDs via claude-api skill |
| 4 | Implement Watcher orchestration (detect→draft→PendingReview→audit) | ⏳ Pending | 1h30m | — | — | |

### Phase 4 — Sidecar + MCP Server  ⏳

**Goal:** One-command MCP server in Claude Desktop driving the lab via ~8 curated task-shaped tools, delegating to the Python SDK through a local sidecar.
**Phase estimate:** ~8h

| # | Task | Status | Estimate | Started | Completed | Notes |
|---|------|--------|----------|---------|-----------|-------|
| 1 | Implement FastAPI sidecar exposing SDK + draft capability | ⏳ Pending | 1h30m | — | — | `adaptyv serve` |
| 2 | Scaffold TS MCP server + sidecar client + auto-spawn | ⏳ Pending | 2h | — | — | |
| 3 | Implement ~8 task-shaped tools with Zod descriptions | ⏳ Pending | 3h | — | — | Not 1:1 CRUD wrappers |
| 4 | MCP tool tests against a stubbed sidecar | ⏳ Pending | 1h30m | — | — | |

### Phase 5 — Evals + Loops  ⏳

**Goal:** Trustworthy, self-improving output — deterministic guards + LLM-judge scoring, plus the three feedback loops.
**Phase estimate:** ~8h

| # | Task | Status | Estimate | Started | Completed | Notes |
|---|------|--------|----------|---------|-----------|-------|
| 1 | Build golden set (results → expected facts) | ⏳ Pending | 1h | — | — | |
| 2 | Implement deterministic guards (no hallucinated numbers, anomalies caught) | ⏳ Pending | 1h30m | — | — | |
| 3 | Implement LLM-judge rubric (accuracy/completeness/tone) + thresholds | ⏳ Pending | 2h | — | — | |
| 4 | Implement eval→improve loop (`make eval` report) | ⏳ Pending | 1h | — | — | |
| 5 | Implement human-feedback flywheel (promote audit rejections → golden set) | ⏳ Pending | 1h30m | — | — | |
| 6 | Implement autonomous watch loop (interval) | ⏳ Pending | 1h | — | — | |

### Phase 6 — Polish & Deliverables  ⏳

**Goal:** Reviewer-ready repo: README, architecture diagram, learning guide, TestPyPI packaging, Loom script.
**Phase estimate:** ~5.25h

| # | Task | Status | Estimate | Started | Completed | Notes |
|---|------|--------|----------|---------|-----------|-------|
| 1 | Write README (value, quickstart, honest scope) | ⏳ Pending | 1h30m | — | — | |
| 2 | Write architecture diagram + data-flow doc | ⏳ Pending | 1h | — | — | |
| 3 | Finalize LEARNING_GUIDE | ⏳ Pending | 1h | — | — | |
| 4 | TestPyPI packaging + install verification | ⏳ Pending | 1h | — | — | |
| 5 | Write 2-minute Loom demo script | ⏳ Pending | 45m | — | — | User records |

---

## Change Log

> The roadmap above reflects the current plan. This log records every deviation from the original design — it is permanent and append-only.

_No changes yet._
