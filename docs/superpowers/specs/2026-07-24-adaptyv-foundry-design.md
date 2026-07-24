# Adaptyv Foundry SDK + MCP Server + Lab Ops Agent — Design Spec

**Status:** Approved; revised v2 after Codex pre-implementation review (schema
corrected from raw spec; sidecar→subprocess bridge; core-first scoping)
**Date:** 2026-07-24
**Author:** AI Engineer take-home for Adaptyv Bio (Lausanne)
**Repo:** `/Users/naloo/Programming/adaptyv-foundry`

---

## 1. Problem & value

Adaptyv Bio runs an automated protein-validation lab. Customers submit protein
sequences through the **Foundry API** and, ~3 weeks later, receive structured
measurements (binding affinity `Kd`, kinetics, expression, etc.). Today the lab
is primarily drivable by engineers via the raw API.

This project delivers a small-but-complete proof of the AI Engineer role's core
mandate — *take capabilities that already exist and make them usable across the
whole company* — in three layers, plus a governance layer that makes the
automation safe to actually adopt:

1. **A clean, typed Python SDK** that wraps the Foundry API (the "control panel").
2. **A TypeScript MCP server** so anyone can drive the lab by talking to Claude
   ("run the lab in plain English").
3. **One real business-process agent** — the **ExperimentWatcher** — that drafts
   customer result emails and flags anomalies (automating a manual chore).
4. **Governance + feedback loops** — human-in-the-loop approval, a tamper-evident
   audit trail, and eval/feedback loops — so the output can be *trusted* and
   *continuously improved*.

**Value to Adaptyv, in plain terms:** the lab becomes usable by the whole team
(not just engineers) through conversation; the tedious "read results → write the
customer update" chore becomes a reviewed first-draft; and every action is
logged and quality-checked so staff and auditors can trust it.

---

## 2. Goals & non-goals

### Goals (success criteria)
- `pip install`-able, typed Python SDK covering **experiments, sequences,
  targets, results** (+ thin coverage of quotes/tokens/whoami).
- **Mock mode** that runs with **no API key** — the same fixtures power the demo,
  the MCP server, and the evals.
- MCP server exposing **~8 curated, task-shaped tools**, installable/runnable with
  one command, that let Claude create experiments, add sequences, check status,
  retrieve results, search targets, and **draft customer updates** in natural
  language.
- **ExperimentWatcher** agent: given completed results (real or mocked), produce
  a professional customer-update email **draft** + a structured **anomaly report**.
- **Human-in-the-loop**: drafts are never auto-sent; explicit human approval;
  critical anomalies hard-block approval until acknowledged.
- **Audit trail**: hash-chained, append-only, queryable; records every
  consequential action with data lineage.
- **Eval suite** scoring drafts for **accuracy / completeness / tone**, plus
  deterministic guards (no hallucinated numbers; anomalies caught).
- **Feedback loops**: offline eval→improve loop; human-feedback flywheel;
  autonomous watch loop.
- Clean GitHub repo with **architecture diagram, README, ROADMAP, LEARNING_GUIDE**,
  and an immediately-runnable mock mode.

### Non-goals (explicit YAGNI)
- Async SDK (sync only).
- Hosted web dashboard / frontend.
- **Real** customer email sending (a "send" is a simulated, audited outbox write).
- Publishing to real PyPI/npm under Adaptyv's namespace (brand-squatting risk).
- Full billing/token lifecycle as MCP tools (SDK methods only).
- Data retention/residency enforcement (documented as a consideration, not built).
- Self-refinement / reflexion loop on drafts (documented as deliberately deferred).

---

## 3. Architecture — "One brain"

The **Python SDK is the single source of truth.** The TypeScript MCP server does
not re-implement HTTP calls — it delegates to the SDK over a local sidecar. The
agent imports the SDK directly. This is the literal embodiment of the role:
*wrap a capability once, reuse it everywhere.*

```
Claude Desktop / Claude Code
      │  natural language (MCP over stdio)
┌─────▼───────────────────────────────────────────────┐
│ MCP SERVER  (TypeScript, @modelcontextprotocol/sdk)  │
│  ~8 task-shaped tools, every param Zod-described      │
│  bridge-client → spawns `python -m adaptyv --json`    │
│  one short-lived Python subprocess per call           │
│  every state-changing tool → audit log                │
└─────┬────────────────────────────────────────────────┘
      │  spawn + JSON (stdin/stdout)
┌─────▼────────────────────────────────────────────────┐
│ adaptyv  (Python)  ◀── SINGLE SOURCE OF TRUTH         │
│  AdaptyvClient: httpx + pydantic v2, sync             │
│  resources/  experiments · sequences · targets · results
│  transport:  LiveTransport | MockTransport (fixtures) │
│  agents/     ExperimentWatcher                         │
│  governance/ approval workflow + audit log             │
│  bridge      `python -m adaptyv --json`  (MCP bridge)  │
│  cli.py      `adaptyv ...`      (Typer, for humans)    │
└─────┬────────────────────────────────────────────────┘
      │  imported directly (Python → Python)
┌─────▼────────────────────────────────────────────────┐
│ ExperimentWatcher agent                               │
│  AnomalyDetector (deterministic rules)                │
│  EmailDrafter    (Claude via Anthropic SDK)           │
│  → PendingReview draft  +  anomaly_report.json        │
│  never sends; critical anomaly hard-blocks approval    │
└─────┬────────────────────────────────────────────────┘
      │  scored / fed by
┌─────▼────────────────────────────────────────────────┐
│ Loops + Evals                                         │
│  eval→improve (offline) · human-feedback flywheel ·    │
│  autonomous watch (runtime)                            │
│  judge: accuracy · completeness · tone + guards        │
└───────────────────────────────────────────────────────┘
```

The MCP exposes both raw SDK operations **and** the agent's `draft_customer_update`
capability through the same subprocess bridge, so drafting works via natural
language in Claude Desktop.

---

## 4. Components

### 4.1 Python SDK (`adaptyv/`) — the core

- **Client:** `AdaptyvClient(api_key=None, mock=False, base_url=...)`, synchronous,
  built on `httpx` + `pydantic v2`.
- **Models** (`models.py`): pydantic models derived from the **raw** OpenAPI schema
  (verified, not summarized) — incl. a generic `Page[T]` pagination envelope
  (`items,total,count,offset`), a **discriminated `ResultSummary` union** on
  `result_type` (`AffinityResult` / `ThermostabilityResult`), distinct list-vs-detail
  models (`ExperimentListItem` vs `ExpInfo`; `SequenceListItem` vs `SequenceInfo`),
  and the real enums (`ExperimentStatus` = draft…done, etc.).
- **Resources** (namespaced, ergonomic):
  - `client.experiments` → `create`, `list`, `get`, `submit`, `results`,
    `cost_estimate`
  - `client.sequences` → `add`, `list`, `get`
  - `client.targets` → `list`, `get`
  - `client.results` → `list`, `get`
  - thin extras: `client.quotes`, `client.tokens.attenuate`, `client.whoami`
- **Transport seam (key design):** a `Transport` Protocol with two
  implementations:
  - `LiveTransport` — real HTTP to Foundry; bearer token from env; **idempotent-only**
    retry honoring `Retry-After` on 429/5xx.
  - `MockTransport` — serves JSON fixtures from `adaptyv/mocks/fixtures/`; **no key
    needed**. This *is* demo mode, and it feeds the MCP demo and the evals.
- **Typed errors:** `AdaptyvError → {AuthError, NotFoundError, RateLimitError,
  ValidationError, TransportError}`.
- **Least-privilege helper:** `client.tokens.attenuate(...)` exposes the API's
  token-attenuation so the agent/MCP can run with a read-mostly scoped token.
- **Packaging:** `pyproject.toml`; import name `adaptyv`; distribution name
  `adaptyv-foundry-sdk` on **TestPyPI**. README shows the aspirational
  `pip install adaptyvbio` with an honest note about the demo namespace.
- **Human CLI (`cli.py`, Typer):** `adaptyv experiments list`, `adaptyv results
  get <id>`, `adaptyv watch`, `adaptyv review`, `adaptyv audit`, plus
  `python -m adaptyv --json <op>` (the MCP bridge entrypoint).

### 4.2 MCP bridge (`python -m adaptyv --json`)

- A subprocess entrypoint the MCP **spawns per call**: reads a JSON op (argv/stdin),
  invokes the SDK (incl. the agent's drafting capability), writes a JSON result or
  typed-error to stdout. **No long-running server, ports, or readiness handshake** —
  this replaces the earlier FastAPI sidecar (see decision #9).
- Maps SDK exceptions → structured JSON errors.
- Writes audit entries for state-changing ops.
- Runs in mock or live mode via env; not a network surface.

### 4.3 MCP server (TypeScript, `mcp/`)

- Built on the official `@modelcontextprotocol/sdk`.
- **~8 curated, task-shaped tools** (NOT 25 CRUD wrappers — the strongest
  prior-art warning):
  1. `list_experiments` — filter/search/status.
  2. `get_experiment_status` — status + progress for one experiment.
  3. `create_experiment_with_sequences` — collapses create + add-sequences.
  4. `add_sequences` — append sequences to a draft.
  5. `search_targets` — find catalog antigens.
  6. `estimate_cost` — cost estimate for a configuration.
  7. `get_results` — retrieve structured results for an experiment.
  8. `draft_customer_update` — invoke the agent to draft a `PendingReview` email.
- Every parameter carries a Zod `.describe()`; each tool has a model-facing
  description written for the agent, not copied from the REST docs.
- **Spawns the bridge per call** (`python -m adaptyv --json`) so the reviewer runs
  one command; degrades with a clear error if Python is unavailable.
- State-changing tools write to the audit log (via the bridge).
- `draft_customer_update` produces a draft **only** — it cannot approve or send.

### 4.4 ExperimentWatcher agent (`adaptyv/agents/`)

- **`AnomalyDetector`** (`anomaly.py`) — pure, deterministic, fully unit-tested,
  driven by a **versioned anomaly policy** (an explicit input, not hardcoded):
  thresholds, positive-control identity, expected-value ranges, units, and
  missing-data semantics. The OpenAPI result carries control identity + relative
  performance but **no authoritative expected range**, so that range lives in the
  policy, not the code. Rules (severities set by policy):
  - all sequences failed / no measurable expression → **critical**
  - positive control outside its policy-defined range → **critical**
  - `Kd` outside policy bounds → warning
  - missing/insufficient replicates → warning
  - Each finding: `{rule, severity, evidence, affected_ids, policy_version}`.
- **`EmailDrafter`** (`email.py`) — Claude (model IDs/params via the `claude-api`
  skill at build time). To keep numbers trustworthy the model emits prose with
  **typed fact placeholders** (e.g. `{{kd_mean_binder1}}`), and the agent then
  **substitutes validated numeric strings** from the source data; a deterministic
  guard rejects any unresolved or unknown placeholder. This is stronger than
  free-form prose (where a model can still invent a figure) but **not a hard
  mathematical guarantee** — hence the eval guard backs it up.
- **`Watcher`** (`watcher.py`) — orchestrates: find newly-completed experiments →
  detect anomalies → draft email → persist as `PendingReview` → record audit +
  data lineage. Runs once or on an interval (see §6 loops).
- **Outputs:** a `PendingReview` draft record + `anomaly_report.json`.

### 4.5 Governance layer (`adaptyv/governance/`)

- **Approval workflow (HITL):**
  - Draft states: `Draft → PendingReview → Approved | Rejected`. A `Sent` state
    exists but "send" = **simulated, audited outbox write** (no real email).
  - The agent only ever produces `PendingReview`.
  - **Claude/the agent cannot approve its own draft.** Approval is a deliberate
    human action (`adaptyv review`), captured with reviewer identity + decision +
    any edits.
  - **Hard-block on critical anomalies:** a draft with a critical finding cannot
    move to `Approved`/`Sent` until a human explicitly **acknowledges** the
    anomaly (recorded in the audit log).
- **Audit trail (`audit.py`):**
  - **Append-only SQLite (core).** Fields: `id, ts, actor (agent|human|token-id),
    action, target (experiment/result/draft id), inputs_ref, outcome`.
  - **Data lineage** per draft: which `result_id`s and which exact numeric values
    fed the email — proving groundedness. The audit keeps references/hashes rather
    than full sensitive payloads (data minimization).
  - **Feedback store (separate table):** the *content* of human edits/corrections
    lives here, referenced by audit events, so the flywheel can reconstruct
    corrected examples (which pure hashes could not).
  - **Hash-chaining + `adaptyv audit verify` (stretch):** each entry seals the
    previous entry's hash for tamper-evidence, with a defined canonical encoding and
    transactional write. This is honestly application-level tamper-*evidence*, not
    tamper-proof; a signed exported head checkpoint is a documented next step.
  - `adaptyv audit` lists/queries.

### 4.6 Feedback loops (`adaptyv/loops/` + eval harness)

1. **Eval→improve loop (offline, core):** `make eval` runs the golden set through
   the drafter, runs the deterministic guards, and reports regressions; failures
   drive prompt/rule fixes. Repeatable, CI-friendly.
2. **Human-feedback flywheel (stretch):** human corrections captured in the
   **feedback store** are **promoted into the golden set** (`adaptyv evals promote
   <draft>`), so real reviewer edits become future regression tests.
3. **Autonomous watch loop (stretch):** `adaptyv watch --interval N` polls for
   newly-completed experiments — keyed by a **durable idempotency key**
   (`experiment_id, result_id, result_version, drafter_version`) so restarts and
   concurrent runs don't duplicate drafts — and drafts+queues them.

### 4.7 Eval suite (`evals/`)

- **Golden set:** `results → expected-email-facts` cases (incl. the anomalous
  fixtures).
- **Two layers:**
  - *Deterministic guards* (pytest, **core, the primary gate**): every fact
    placeholder resolves to a source value (no invented numbers); required facts
    present; critical anomalies flagged; a draft is never approvable while a
    critical anomaly is unacknowledged.
  - *LLM-judge* (**stretch**, Anthropic SDK): rubric scoring **accuracy /
    completeness / tone**, reported as an evaluation **artifact** (scores + trend),
    **not a hard CI gate** — it needs a key and has run-to-run variance.
- Judge/drafting model IDs confirmed via the `claude-api` skill at build time.

---

## 5. Mock mode, fixtures & data model

- Fixtures under `adaptyv/mocks/fixtures/*.json`, validated by a **contract test**
  against the **pinned OpenAPI JSON Schema** (`tests/data/openapi.json`, sha256
  recorded) *and* the pydantic models — so mock data cannot drift from the real API
  contract. Lists carry the real `{items,total,count,offset}` envelope.
- Fixture scenarios include:
  - a healthy `done` experiment with affinity + kinetic results (happy path),
  - **all-sequences-failed** (critical anomaly),
  - **control-out-of-policy** (critical anomaly),
  - experiments in `draft` / `in_production` / `in_review` states (for status tools).
- The same fixtures drive: SDK unit tests, MCP demo, agent runs, and the eval
  golden set — one source of demo truth.

---

## 6. Error handling

- **SDK:** typed exception hierarchy; ret/backoff on 429/5xx; validation errors on
  malformed requests before hitting the wire.
- **Bridge:** SDK exceptions → structured JSON errors on stdout.
- **MCP:** tool errors returned as structured, model-readable messages (so Claude
  can recover or explain), never raw stack traces.
- **Agent:** if results are incomplete/missing, degrade gracefully; the anomaly
  report is always produced; a draft is never fabricated from missing data.

---

## 7. Testing strategy (TDD)

- **SDK:** unit tests against `MockTransport`; contract test validating every
  fixture against the pinned OpenAPI schema + pydantic models; error-path tests
  (auth/404/429); mock/live shape parity (pagination envelopes).
- **AnomalyDetector:** exhaustive deterministic unit tests per rule + severity.
- **Governance:** audit hash-chain integrity tests (append + tamper detection);
  approval state-machine tests incl. the critical-anomaly hard-block; test that
  the agent cannot self-approve.
- **MCP:** tool tests against a stubbed bridge (params validated, right op called,
  errors surfaced).
- **Evals:** deterministic guards run in CI (the gate); LLM-judge behind a marker
  (needs a key), reported as an artifact rather than a gate.
- Nothing is claimed "done/passing" without `verification-before-completion`
  output.

---

## 8. Security & data governance

- **Least privilege:** SDK token-attenuation helper; agent/MCP run read-mostly
  where possible.
- **Secrets:** API keys via env only; never written to logs or the audit store.
- **AI data boundary:** result data sent to Claude for drafting is a
  governance-relevant flow — documented explicitly (what leaves the system, to
  whom); prompt + injected data are inspectable.
- **Data minimization:** audit log stores references/hashes, not full sensitive
  payloads.
- **Retention / residency:** documented as considerations; not implemented (YAGNI).
- **Human oversight & auditability:** the HITL gate + append-only audit (hash-chained
  in the stretch tier) map onto recognized governance principles (human oversight,
  auditability, least privilege, data minimization) without overclaiming an
  enterprise GRC stack.

---

## 9. Repo layout & deliverables

```
adaptyv-foundry/
├── README.md                      # value, quickstart, architecture diagram, honest scope
├── ROADMAP.md                     # phases/tasks/estimates (created after spec approval)
├── LEARNING_GUIDE.md              # concept explanations (created after spec approval)
├── pyproject.toml
├── Makefile                       # demo, test, eval, bridge
├── adaptyv/                       # Python SDK (single source of truth)
│   ├── client.py  models.py  transport.py  live_transport.py  errors.py
│   ├── resources/                 # experiments, sequences, targets, results
│   ├── agents/                    # anomaly.py, email.py, watcher.py
│   ├── governance/                # approval.py, audit.py, feedback.py
│   ├── loops/                     # watch + flywheel helpers (stretch)
│   ├── __main__.py  cli.py        # `python -m adaptyv --json` bridge + Typer CLI
│   └── mocks/fixtures/*.json
├── mcp/                           # TypeScript MCP server
│   ├── src/index.ts  src/bridge-client.ts  src/tools/*.ts
│   └── package.json  tsconfig.json
├── evals/                         # golden set + guards (+ judge, stretch)
├── tests/data/openapi.json        # pinned OpenAPI spec (contract test)
└── docs/
    ├── superpowers/specs|plans/   # this document + phase plans
    └── architecture.md            # diagram + data-flow + governance notes
```

**Deliverables:** GitHub repo; installable SDK (TestPyPI *stretch*); one-command MCP
+ mock mode; ExperimentWatcher producing draft + anomaly report; eval suite; README +
architecture diagram + ROADMAP + LEARNING_GUIDE; a **script** for the 2-minute Loom
(recording is the user's).

---

## 10. Decisions log (resolved forks + rationale)

| # | Decision | Choice | Why |
|---|----------|--------|-----|
| 1 | SDK build approach | Hand-written typed `httpx`+`pydantic` (spec as type source) | JD is "wrap APIs cleanly"; API is small (~25 endpoints); generated blobs show no judgment |
| 2 | SDK distribution | Local + **TestPyPI**, honest README | Avoids brand-squatting Adaptyv's PyPI namespace during an interview |
| 3 | Demo surface | **CLI + MCP only** (no web dashboard) | Cleanest for a 2-min Loom; least scope risk |
| 4 | Eval stack | **Hand-rolled LLM-judge + pytest** | Transparent, dependency-light, easy to defend as own work |
| 5 | MCP↔SDK coupling | **Option A — one brain** (MCP → SDK) | Literal embodiment of the role; single source of truth |
| 6 | Audit trail | **Append-only SQLite** (hash-chaining = stretch) | Auditability now; tamper-evidence as a labeled enhancement |
| 7 | Anomaly gate | **Hard-block until human acknowledges** | Real oversight, not advisory theater |
| 8 | Loops | eval→improve (core) + flywheel + autonomous watch (stretch) | Coherent "loop engineering" reusing feedback store + evals; self-refinement deferred |
| 9 | MCP↔SDK **mechanism** | **Subprocess JSON bridge** (`python -m adaptyv --json`), not FastAPI sidecar | Codex review + user: stdio-MCP auto-spawning a web server hides port/readiness/cleanup complexity not worth a take-home |
| 10 | Schema source of truth | Models derived from **raw parsed** OpenAPI JSON + pinned contract test | An initial summarized `WebFetch` hallucinated the schema; raw parse + pinned schema prevents recurrence |
| 11 | Scope strategy | **Core-first**; hash-chain, flywheel, autonomous watch, live judge, TestPyPI = stretch | Codex review: protect the hard requirements from being left shallow |

---

## 11. Risks & open questions

- **Cross-language coupling** (MCP spawns the Python bridge per call) adds a Python
  dependency for the MCP demo. Mitigation: per-call subprocess (no server lifecycle)
  + clear error; document the one prerequisite.
- **No live API key** — all live-path code is exercised only against `MockTransport`
  and fixtures shaped from the OpenAPI schema; live behavior is best-effort until a
  key exists. Mitigation: the contract test binds fixtures to the **pinned** real
  schema (sha256 recorded), and mock/live shape parity is tested.
- **Schema fidelity** — an initial summarized fetch of the OpenAPI spec hallucinated
  fields/enums/envelopes; a Codex pre-implementation review caught it. Mitigation:
  models are now derived from **raw parsed JSON**, never a summary; the pinned
  contract test guards against regressions. (See `feedback_verify_api_schemas_raw`.)
- **LLM cost/determinism in evals** — judge calls cost tokens and vary; mitigate
  with a small golden set and deterministic guards as the primary gate (judge is a
  reported artifact, not a CI gate).
- **Model IDs/params** — confirmed via the `claude-api` skill at implementation
  time, not hardcoded from memory.
