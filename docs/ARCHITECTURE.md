# Architecture

## System diagram

```
┌─────────────────────────┐
│  Claude Desktop / Code   │  a person, driving the lab in plain English
└────────────┬─────────────┘
             │ MCP over stdio
             ▼
┌─────────────────────────┐
│   MCP Server (TS)        │  mcp/  — 8 task-shaped tools, not 1:1 CRUD wrappers
│   BridgeClient            │
└────────────┬─────────────┘
             │ spawn `python -m adaptyv --json <op>` per call, JSON in/out
             ▼
┌─────────────────────────┐
│   Subprocess Bridge       │  adaptyv/bridge.py — the only thing the MCP talks to
│   handle_request()        │  always exits 0; failure is `{"ok": false, "error": {...}}`
└────────────┬─────────────┘
             │
     ┌───────┴────────────────────────────┐
     ▼                                     ▼
┌───────────────────┐          ┌─────────────────────────────┐
│  AdaptyvClient      │          │  Watcher (governed agent)    │
│  (SDK, mock|live)   │◀────────│  AnomalyDetector + EmailDrafter│
└─────────┬───────────┘          └───────────────┬──────────────┘
          │                                       │
   ┌──────┴──────┐                        ┌───────┴────────┐
   ▼             ▼                        ▼                ▼
MockTransport  LiveTransport         ApprovalStore      AuditLog
(fixtures)     (httpx→real API)      (HITL state          (hash-chained,
                                      machine)             append-only)
```

Everything below the bridge line is pure Python, one process, one codebase — the MCP server never re-implements any lab logic; it only translates a tool call into a JSON request and prints the JSON response back to Claude.

## Why a subprocess bridge, not a sidecar

Two alternatives were considered before building this. An auto-spawned FastAPI sidecar (a long-running local web server the MCP starts and calls over `localhost`) was rejected during pre-implementation review: starting a web server from a stdio MCP hides real complexity — port allocation, a readiness handshake, process cleanup, version skew between the MCP and the server it spawned. A separate, thinner TypeScript client that re-implements the lab API itself was rejected because it duplicates logic across two languages — two brains to keep in sync, double the bugs. The subprocess bridge is the middle path: `python -m adaptyv --json <op>` is invoked fresh per call, does the real work through the SDK, prints one JSON line, and exits. No server lifecycle to manage; the Python SDK stays the single source of truth.

## The 8 MCP tools

Task-shaped, not CRUD wrappers over every endpoint:

| Tool | Bridge op | What it does |
|---|---|---|
| `list_experiments` | `list_experiments` | Search/filter/sort experiments |
| `get_experiment_status` | `get_experiment_status` | Full status + workflow state for one experiment |
| `create_experiment_with_sequences` | `create_experiment_with_sequences` | Create an experiment and attach sequences in one step |
| `add_sequences` | `add_sequences` | Append sequences to a draft experiment |
| `search_targets` | `search_targets` | Search the target-antigen catalog |
| `get_results` | `get_results` | Fetch structured results for a completed experiment |
| `estimate_cost` | `estimate_cost` | Cost estimate for an experiment configuration, before creating it |
| `draft_customer_update` | `draft_customer_update` | Runs the Watcher for one experiment; returns a `PendingReview` draft — never sent automatically |

## End-to-end flow 1: creating an experiment via MCP

1. A user asks Claude to create an affinity experiment against a target.
2. Claude calls the `create_experiment_with_sequences` MCP tool; the Zod schema validates `experiment_type`, optional `method`/`n_replicates`, and the sequence list shape before the tool handler ever runs.
3. `BridgeClient.call()` spawns `python -m adaptyv --json`, writing `{"op": "create_experiment_with_sequences", "params": {...}}` to stdin.
4. `bridge.py`'s `_op_create_experiment_with_sequences` translates the flat sequence list into the name-keyed dict the real Foundry API requires (`_sequences_by_name` — raises a structured `BridgeError` if two sequences would collide under the same name, rather than silently dropping one), then constructs an `ExperimentSpec`.
5. **`ExperimentSpec`'s own pydantic validator enforces the real assay matrix** (from the OpenAPI spec's authoritative table) before any request is sent: `method` is required for affinity/screening and rejected for everything else; `target_id` is required for affinity/screening/epitope_binning and rejected otherwise; at least one sequence is required. An invalid request is rejected here — in mock mode exactly as it would be by the live API — not silently accepted.
6. `AdaptyvClient.experiments.create()` sends the request through `MockTransport` (or `LiveTransport`, unchanged code path) and returns a typed `CreateExpResponse`.
7. `handle_request()` wraps the result as `{"ok": true, "result": {...}}` (or a structured `{"ok": false, "error": {...}}` on any `AdaptyvError`/validation failure) and the bridge process exits 0 either way — failure is always signaled through the `ok` field, never a crash or nonzero exit code.
8. The MCP tool formats the JSON result as text content back to Claude.

## End-to-end flow 2: watching for results and drafting a customer update

1. `adaptyv watch` (CLI) or the `draft_customer_update` MCP tool constructs a `Watcher(client, AnomalyDetector, drafter, ApprovalStore, conn)` — **`Watcher` and `ApprovalStore` must share the exact same sqlite connection object** (`ApprovalStore.shares_connection_with()` is asserted in `Watcher.__init__`; a mismatch raises immediately rather than silently breaking the atomicity guarantee below).
2. For each experiment's result not already in the durable `watcher_processed` table (keyed by `experiment_id:result_id:drafter_model`), `Watcher.run()`:
   - Runs `AnomalyDetector.detect(result)` — a fixed, versioned policy (`AnomalyPolicy`), never an LLM judgment call. Four deterministic rules: all sequences failed, positive control out of policy range, Kd implausible, missing replicates. The first two are `critical`; the rest are `warning`.
   - Runs `EmailDrafter.draft(result, findings)` — see "How hallucination is actually prevented" below.
   - Calls `ApprovalStore.create_draft(..., before_commit=lambda draft_id: <write the watcher_processed row>)`. The draft insert, its audit entry, and the idempotency marker all commit as **one sqlite transaction** — if any of the three fails, all three roll back together, so a crash mid-write can never produce a draft with no marker (which would otherwise cause a duplicate draft on retry).
3. Any exception during detection, drafting, or draft creation for one result is caught per-result — recorded in `watcher.errors`, not raised — so one bad result never aborts the rest of the batch. This is the single most-repeated lesson of this codebase: three separate places (the Watcher loop itself, the subprocess bridge dispatch, and the offline eval runner) each independently needed this same per-item isolation before they were correct.
4. The resulting draft is `PENDING_REVIEW`. A human runs `adaptyv review approve` (or the equivalent governance flow) — `ApprovalStore.approve()` refuses a non-human `Actor` outright (`SelfApprovalError`), and refuses any draft with an unacknowledged critical anomaly (`AnomalyNotAcknowledgedError`) until `review ack` is called first.
5. Every state transition — draft created, anomaly acknowledged, approved, rejected, sent — is written to `AuditLog` as one more link in a hash chain: each entry's hash covers its own content plus the previous entry's hash, so altering or deleting an old entry breaks every hash after it. `adaptyv audit verify` recomputes the whole chain. This is **tamper-evident, not tamper-proof** — a determined attacker with direct sqlite access could recompute the entire chain from scratch; real tamper-proofing needs an externally-pinned "head" hash or write-once storage, which is out of scope here and said so directly rather than oversold.

## How hallucination is actually prevented

This went through three rounds of external review before landing on a design that actually holds — worth understanding *why*, not just *what*, because the first two designs looked reasonable and both were wrong in the same way.

**What didn't work:** both earlier designs were *detection*-based — check whether a number the model wrote matches something in an allowed set (a regex over "known" placeholders, then a "grounded numbers" set-membership check). Both were eventually defeated, because a detection rule can only reject the specific patterns its author thought to enumerate. The final review's exact counterexample: the model types `Kd was 1.20e-09 M` as plain prose (no placeholder at all) — and the number is *correct*, so a grounded-numbers check that just asks "does this number appear somewhere in the facts" waves it through, even though the model never actually used the verified substitution path.

**What works, and why it's structurally different:** `substitute_facts()` (`adaptyv/agents/email.py`) is **deny-by-default**. Before attempting any substitution, it strips every well-formed `{{fact_id}}` span out of the model's raw output and checks whether any digit remains — if one does, the whole draft is rejected, full stop, regardless of whether that digit happens to be correct. A number can reach a persisted draft through exactly one path: a `{{fact_id}}` placeholder that resolves against a fact sheet built from the actual `ResultInfo` data. After substitution, any leftover `{` or `}` character (an empty, unclosed, or malformed placeholder) is also rejected — one generic check, rather than trying to enumerate every malformed shape a regex might miss.

Anomaly-finding evidence (e.g. "policy requires 2 replicates") legitimately contains numbers the drafter is instructed to echo verbatim — so those numbers are templated into their own placeholders (`ev_1_1`, `ev_1_2`, ...) *before* the prompt is even built, meaning "copy this evidence text exactly" can never reintroduce a raw number either. Fact IDs are an opaque counter (`kd_1`, `kd_2`, ...), not derived from sequence names, which also eliminates an entire class of name-collision bugs by construction rather than by disambiguation logic.

The offline eval suite (`evals/guards.py`) does **not** re-implement any part of this check — it used to, and that duplicate implementation is exactly how the guarantee drifted out of sync across two review rounds. The eval suite instead runs `EmailDrafter.draft()` for real (against a deterministic fake Anthropic client, so it's still fully offline) and treats any raised exception as a failed case. There is now exactly one implementation of "no raw numbers reach a draft," not two.

## Idempotency

Two independent mechanisms guarantee re-running never duplicates work:

- **Watcher**: a durable `watcher_processed` sqlite table, keyed by `experiment_id:result_id:drafter_model`, checked before any drafting is attempted and written atomically with the draft+audit commit (see flow 2, step 2).
- **Eval-to-golden-set flywheel** (`evals/flywheel.py`): `promote_corrections()` is idempotent by `experiment_id` — re-running it never promotes the same correction twice.

## What's deliberately not built

See the README's "Honest scope and limitations" section and `ROADMAP.md`'s Change Log for the full, dated list of every review finding and what was or wasn't fixed and why. The short version: cross-process/cross-connection concurrency, a live LLM-judge eval tier, and full pagination/filtering in mock mode are all explicitly out of scope, not overlooked.
