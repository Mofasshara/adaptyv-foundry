# Adaptyv Foundry SDK + MCP Server + Lab Ops Agent — Design Spec

**Status:** Approved design (pending written-spec review)
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
│  sidecar-client → HTTP localhost                      │
│  auto-spawns the Python sidecar on startup            │
│  every state-changing tool → audit log                │
└─────┬────────────────────────────────────────────────┘
      │  localhost JSON
┌─────▼────────────────────────────────────────────────┐
│ adaptyv  (Python)  ◀── SINGLE SOURCE OF TRUTH         │
│  AdaptyvClient: httpx + pydantic v2, sync             │
│  resources/  experiments · sequences · targets · results
│  transport:  LiveTransport | MockTransport (fixtures) │
│  agents/     ExperimentWatcher                         │
│  governance/ approval workflow + hash-chained audit    │
│  server.py   `adaptyv serve`   (FastAPI sidecar)       │
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
capability through the same sidecar, so drafting works via natural language in
Claude Desktop.

---

## 4. Components

### 4.1 Python SDK (`adaptyv/`) — the core

- **Client:** `AdaptyvClient(api_key=None, mock=False, base_url=...)`, synchronous,
  built on `httpx` + `pydantic v2`.
- **Models** (`models.py` / `models/`): pydantic models mirroring the OpenAPI
  schemas — `ExpInfo`, `CreateExpRequest/Response`, `SequenceInfo`,
  `SequenceAddRequest`, `TargetInfo/Details`, `ResultInfo`, `ResultSummary`,
  `AffinityResult`, `AffinityReplicate`, `KineticInterval`, etc.
- **Resources** (namespaced, ergonomic):
  - `client.experiments` → `create`, `list`, `get`, `submit`, `results`,
    `cost_estimate`
  - `client.sequences` → `add`, `list`, `get`
  - `client.targets` → `list`, `get`
  - `client.results` → `list`, `get`
  - thin extras: `client.quotes`, `client.tokens.attenuate`, `client.whoami`
- **Transport seam (key design):** a `Transport` Protocol with two
  implementations:
  - `LiveTransport` — real HTTP to Foundry; bearer token from env; retry + backoff
    on 429/5xx.
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
  get <id>`, `adaptyv serve`, `adaptyv watch`, `adaptyv review`, `adaptyv audit`.

### 4.2 Sidecar (`server.py`, FastAPI)

- `adaptyv serve` starts a localhost FastAPI app exposing SDK operations **and**
  the agent's drafting capability as JSON endpoints.
- Maps SDK exceptions → HTTP status codes.
- Writes audit entries for state-changing calls.
- Bound to localhost only; token via env; not a public surface.

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
- **Auto-spawns the sidecar** on startup (child process) so the reviewer runs one
  command; degrades with a clear error if Python is unavailable.
- State-changing tools write to the audit log (via the sidecar).
- `draft_customer_update` produces a draft **only** — it cannot approve or send.

### 4.4 ExperimentWatcher agent (`adaptyv/agents/`)

- **`AnomalyDetector`** (`anomaly.py`) — pure, deterministic, fully unit-tested.
  Rule set (thresholds configurable):
  - all sequences failed / no measurable expression → **critical**
  - positive control outside expected range → **critical**
  - `Kd` outside plausible bounds → warning
  - missing/insufficient replicates → warning
  - Each finding: `{rule, severity, evidence, affected_ids}`.
- **`EmailDrafter`** (`email.py`) — Claude (latest model; exact IDs/params
  confirmed via the `claude-api` skill at build time) turns `ResultSummary` +
  anomaly findings into a plain-English customer update. **Numbers are injected
  from source data, never generated by the model** (the prompt receives structured
  facts; the model composes prose around them).
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
  - **Hash-chained, append-only SQLite** — each entry stores a hash of the
    previous entry (tamper-evident chain), verifiable via `adaptyv audit verify`.
  - Fields: `id, ts, actor (agent|human|token-id), action, target (experiment/
    result/draft id), inputs_ref, outcome, prev_hash, entry_hash`.
  - **Data lineage** per draft: which `result_id`s and which exact numeric values
    fed the email — proving groundedness.
  - Stores references/hashes rather than dumping full sensitive payloads
    (data minimization).
  - `adaptyv audit` lists/queries; `adaptyv audit verify` checks the chain.

### 4.6 Feedback loops (`adaptyv/loops/` + eval harness)

1. **Eval→improve loop (offline):** `make eval` runs the golden set through the
   drafter, scores with the judge, and reports regressions; failures drive
   prompt/rule fixes. Explicit, repeatable, CI-friendly.
2. **Human-feedback flywheel:** human edits/rejections captured in the audit log
   can be **promoted into the eval golden set** (`adaptyv evals promote <draft>`),
   so real reviewer corrections become future regression tests. The governance
   layer doubles as the improvement data source.
3. **Autonomous watch loop (runtime):** `adaptyv watch --interval N` polls for
   newly-completed experiments and drafts+queues them, repeating — makes the agent
   operational, not one-shot.

### 4.7 Eval suite (`evals/`)

- **Golden set:** `results → expected-email-facts` cases (incl. the anomalous
  fixtures).
- **Two layers:**
  - *Deterministic guards* (pytest): every number in the email traces to source
    data (no hallucination); required facts present; critical anomalies flagged;
    email never emitted in an approvable state when a critical anomaly exists.
  - *LLM-judge* (G-Eval style, Anthropic SDK): rubric scoring **accuracy /
    completeness / tone**, each with a pass threshold; regressions fail CI.
- Judge model and drafting model confirmed via the `claude-api` skill at build
  time (default lean: a current Sonnet-class model for drafting; a strong model
  for judging).

---

## 5. Mock mode, fixtures & data model

- Fixtures under `adaptyv/mocks/fixtures/*.json`, validated against the pydantic
  models by a **contract test** (so mock data can never drift from the real schema
  shape).
- Fixture scenarios include:
  - a healthy completed experiment with affinity + kinetic results (happy path),
  - **all-sequences-failed** (critical anomaly),
  - **control-out-of-range** (critical anomaly),
  - experiments in Draft / InReview / running states (for status tools).
- The same fixtures drive: SDK unit tests, MCP demo, agent runs, and the eval
  golden set — one source of demo truth.

---

## 6. Error handling

- **SDK:** typed exception hierarchy; ret/backoff on 429/5xx; validation errors on
  malformed requests before hitting the wire.
- **Sidecar:** SDK exceptions → HTTP codes with structured error bodies.
- **MCP:** tool errors returned as structured, model-readable messages (so Claude
  can recover or explain), never raw stack traces.
- **Agent:** if results are incomplete/missing, degrade gracefully; the anomaly
  report is always produced; a draft is never fabricated from missing data.

---

## 7. Testing strategy (TDD)

- **SDK:** unit tests against `MockTransport`; contract test validating every
  fixture against pydantic models; error-path tests (auth/404/429).
- **AnomalyDetector:** exhaustive deterministic unit tests per rule + severity.
- **Governance:** audit hash-chain integrity tests (append + tamper detection);
  approval state-machine tests incl. the critical-anomaly hard-block; test that
  the agent cannot self-approve.
- **MCP:** tool tests against a stubbed sidecar (params validated, right endpoint
  called, errors surfaced).
- **Evals:** deterministic guards run in CI; LLM-judge run behind a marker (needs
  API key) with thresholds.
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
- **Human oversight & auditability:** the HITL gate + hash-chained audit map onto
  recognized governance principles (human oversight, auditability, least
  privilege, data minimization) without overclaiming an enterprise GRC stack.

---

## 9. Repo layout & deliverables

```
adaptyv-foundry/
├── README.md                      # value, quickstart, architecture diagram, honest scope
├── ROADMAP.md                     # phases/tasks/estimates (created after spec approval)
├── LEARNING_GUIDE.md              # concept explanations (created after spec approval)
├── pyproject.toml
├── Makefile                       # demo, test, eval, serve
├── adaptyv/                       # Python SDK (single source of truth)
│   ├── client.py  models*  transport.py
│   ├── resources/                 # experiments, sequences, targets, results, ...
│   ├── agents/                    # anomaly.py, email.py, watcher.py
│   ├── governance/                # approval.py, audit.py
│   ├── loops/                     # watch + flywheel helpers
│   ├── server.py  cli.py
│   └── mocks/fixtures/*.json
├── mcp/                           # TypeScript MCP server
│   ├── src/index.ts  src/sidecar-client.ts  src/tools/*.ts
│   └── package.json  tsconfig.json
├── evals/                         # golden set + judge + guards
└── docs/
    ├── superpowers/specs/         # this document
    └── architecture.md            # diagram + data-flow + governance notes
```

**Deliverables:** GitHub repo; TestPyPI-published SDK; one-command MCP + mock
mode; ExperimentWatcher producing draft + anomaly report; eval suite; README +
architecture diagram + ROADMAP + LEARNING_GUIDE; a **script** for the 2-minute
Loom (recording is the user's).

---

## 10. Decisions log (resolved forks + rationale)

| # | Decision | Choice | Why |
|---|----------|--------|-----|
| 1 | SDK build approach | Hand-written typed `httpx`+`pydantic` (spec as type source) | JD is "wrap APIs cleanly"; API is small (~25 endpoints); generated blobs show no judgment |
| 2 | SDK distribution | Local + **TestPyPI**, honest README | Avoids brand-squatting Adaptyv's PyPI namespace during an interview |
| 3 | Demo surface | **CLI + MCP only** (no web dashboard) | Cleanest for a 2-min Loom; least scope risk |
| 4 | Eval stack | **Hand-rolled LLM-judge + pytest** | Transparent, dependency-light, easy to defend as own work |
| 5 | MCP↔SDK coupling | **Option A — one brain** (MCP → SDK sidecar) | Literal embodiment of the role; single source of truth |
| 6 | Audit trail | **Hash-chained append-only SQLite** | Tamper-evident; strong governance story; low cost |
| 7 | Anomaly gate | **Hard-block until human acknowledges** | Real oversight, not advisory theater |
| 8 | Loops | eval→improve + human-feedback flywheel + autonomous watch | Coherent "loop engineering" reusing audit+evals; self-refinement deferred |

---

## 11. Risks & open questions

- **Cross-language runtime coupling** (MCP spawns Python sidecar) adds a Python
  dependency for the MCP demo. Mitigation: auto-spawn + clear error; document the
  one prerequisite.
- **No live API key** — all live-path code is exercised only against `MockTransport`
  and fixtures shaped from the OpenAPI schema; live behavior is best-effort until a
  key exists. Mitigation: contract tests bind fixtures to the real schema.
- **LLM cost/determinism in evals** — judge calls cost tokens and vary; mitigate
  with a small golden set, thresholds, and deterministic guards as the primary
  gate.
- **Model IDs/params** — confirmed via the `claude-api` skill at implementation
  time, not hardcoded from memory.
