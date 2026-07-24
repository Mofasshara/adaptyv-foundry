# Learning Guide — Adaptyv Foundry SDK + MCP + Lab Ops Agent

> A living explainer for every concept, tool, and decision in this project.
> Written in two layers: plain-English analogy first, technical mechanism second.
> Updated as we build. Last updated: 2026-07-24 (pre-implementation; based on the approved design).

---

## The big picture

Adaptyv Bio runs an automated protein lab: customers send in protein sequences, and weeks later get back measurements (how tightly the protein binds, how stable it is). All of this runs through an online system — the **Foundry API**. Today you basically need to be an engineer to use it.

This project makes that lab usable by *everyone* at Adaptyv and automates one tedious human chore. It has three visible pieces and one invisible-but-critical one:
1. a clean **toolkit** (SDK) so software can talk to the lab without reinventing the plumbing,
2. a **talk-to-it interface** (MCP server) so anyone can drive the lab by chatting with Claude,
3. an **assistant** (ExperimentWatcher) that reads finished results and drafts the customer update email,
4. a **trust layer** — human sign-off, a tamper-evident logbook, and automatic quality-grading — so the automation is safe to actually adopt.

---

## Architecture at a glance

```
Claude Desktop / Code                         ← a person, talking in plain English
   │
   ▼  (MCP over stdio)
MCP SERVER (TypeScript)                        ← the receptionist: turns chat into actions
   │
   ▼  (spawns per call)
adaptyv SDK (Python)  ◀── SINGLE SOURCE OF TRUTH   ← the translator: speaks fluent "lab API"
   ├─ transport: Live | Mock (fixtures)        ← real lab line, or a rehearsal stand-in
   ├─ agents: ExperimentWatcher                ← the assistant that drafts emails
   └─ governance: approval gate + audit log    ← the sign-off desk + the sealed logbook
   │
   ▼
Evals + Loops                                  ← the quality inspector + the improvement flywheel
```

---

## Part 1 — The SDK Layer

*Its job: give software one clean, typed, reliable way to talk to the lab.*

### Typed models (pydantic v2) — the labelled forms

**What it is**
Pydantic models are **pre-printed forms with labelled, type-checked boxes**. Instead of receiving a shapeless blob of data from the lab and hoping the "Kd value" field exists, you pour the data into a form that *knows* what fields must be present and what type each is — and rejects anything malformed at the door.

**The problem it solves**
Without typed models, every part of the code accesses raw dictionaries (`data["summary"][0]["value"]`) and a missing or renamed field explodes deep inside the agent, at runtime, in production. Typed models catch the mismatch immediately, at the boundary, with a clear message.

**How it works**
1. We read the lab's official API description (the OpenAPI spec) to learn the exact shape of every response.
2. We hand-write a Python class per shape (`AffinityResult`, `ResultSummary`, …) declaring each field and its type.
3. When data arrives, `Model.model_validate(data)` checks it and hands back a typed object with autocomplete and guarantees.

**Why we chose it for this project**
Alternative considered: auto-generating the whole SDK from the spec (tools like openapi-python-client). Rejected — generated code is un-idiomatic and shows no engineering judgment, and the API is small enough (~25 endpoints) that hand-written models are both cleaner *and* the actual thing being evaluated. We still use the spec as the source of truth for field names.

**Key things to know**
- Models are set to *ignore* unknown fields, so if the lab adds a field tomorrow, nothing breaks (forward-compatibility).
- A **contract test** validates every mock fixture against these models, so our rehearsal data can never silently drift from the real schema.

### Pluggable transport + mock mode — the rehearsal stand-in

**What it is**
The transport is the **phone line to the lab**, and it's swappable. `LiveTransport` is the real line (needs credentials). `MockTransport` is a **rehearsal stand-in** that reads canned answers from files, so the whole system runs convincingly with no key and no network.

**The problem it solves**
We have no live API key, and a reviewer cloning the repo has none either. Without a mock, nothing could be demoed or tested. Also, tests that hit a real lab are slow, flaky, and cost money.

**How it works**
1. The client doesn't know or care which line it's using — it just calls `transport.request(method, path)`.
2. `AdaptyvClient(mock=True)` plugs in `MockTransport`, which routes each request to a matching JSON fixture.
3. The *same* fixtures feed the tests, the Claude demo, and the eval suite — one source of demo truth.

```
AdaptyvClient ──▶ Transport (interface)
                   ├── LiveTransport  → real Foundry API
                   └── MockTransport  → fixtures/*.json
```

**Why we chose it for this project**
Alternative considered: a separate fake HTTP server process. Rejected as heavier to run and explain; an in-process stand-in behind the same interface is simpler and makes `mock=True` a one-word switch.

**Key things to know**
- This "swap the implementation behind a shared interface" idea is the **dependency-inversion / adapter pattern** — the single most reused trick in the whole project (it reappears in the audit store and the judge).

### TestPyPI packaging — shipping the toolkit honestly

**What it is**
Packaging turns our folder of code into an installable product (`pip install ...`). **TestPyPI** is the *dress-rehearsal* version of the public Python package registry.

**The problem it solves**
"It works on my machine" isn't a deliverable. A reviewer needs to install it like a real library. But publishing to the *real* registry under the name `adaptyvbio` would be squatting a brand that belongs to the company we're interviewing with.

**How it works**
1. `pyproject.toml` declares the package name, version, dependencies, and CLI entry point.
2. We publish to TestPyPI under a clearly-unofficial name (`adaptyv-foundry-sdk`).
3. The README shows the aspirational `pip install adaptyvbio` command with an honest note about the demo namespace.

**Why we chose it for this project**
Real-PyPI publish was rejected on reputational grounds (brand squatting); a purely-local package was rejected as less convincing. TestPyPI is the honest middle: really installable, no land-grab.

---

## Part 2 — The Governance Layer

*Its job: make the automation safe and accountable — nothing reaches a customer unreviewed, and everything is recorded.*

### Hash-chained audit log — the wax-seal logbook

**What it is**
It's a **logbook where each page is sealed with a wax stamp made from the previous page.** Every meaningful action (experiment created, email drafted, anomaly flagged, human approved) is a new line. Each line carries a fingerprint of the line before it — so if anyone edits or deletes an old entry, every seal after it stops matching and the tampering is obvious.

**The problem it solves**
A plain log can be quietly edited after the fact — useless if a customer disputes a result or an auditor asks "prove this wasn't altered." Without tamper-evidence, "we have logs" doesn't mean "we have trustworthy logs."

**How it works**
1. Each entry records: who, what action, on what, when, outcome — plus **data lineage** (which exact result numbers fed a draft).
2. Before saving, we compute a fingerprint (hash) of *this* entry's contents **plus the previous entry's fingerprint**.
3. To verify integrity later, we recompute the whole chain; any mismatch pinpoints the first altered entry.

```
Entry 1 ─hash1─▶ Entry 2 (contains hash1) ─hash2─▶ Entry 3 (contains hash2) ─▶ ...
Edit Entry 2 → hash2 changes → Entry 3's stored hash no longer matches → tamper detected
```

**Why we chose it for this project**
Alternatives considered: a plain JSONL file (simplest, but no tamper-evidence) and a full external audit service (overkill for a take-home). Hash-chained SQLite is the sweet spot — queryable, tamper-evident, near-zero extra cost, and it tells a strong governance story. What we gave up: it's tamper-*evident*, not tamper-*proof* (a determined attacker could recompute the whole chain) — real systems add signing or write-once storage; we document that as the next step.

**Key things to know**
- The log stores *references and hashes*, not full sensitive payloads — that's **data minimization** (don't hoard sensitive data you don't need to).
- The same log doubles as the data source for the improvement flywheel (see Part 5).

### Human-in-the-loop approval — the sign-off desk

**What it is**
A rule that the AI is a **fast first-drafter, never the sender.** Every customer email stops at a person's desk, who reviews, edits, and explicitly approves before anything goes out. Critically, the AI **cannot approve its own work.**

**The problem it solves**
An AI emailing a customer a wrong binding number, unsupervised, is exactly the failure that makes staff distrust and abandon automation — and could embarrass Adaptyv with a client. The gate removes that failure mode entirely.

**How it works**
1. The agent produces a draft in state `PendingReview` — never `Sent`.
2. A human runs the review step, which records their identity, decision, and any edits in the audit log.
3. If the draft carries a **critical anomaly** (e.g. all sequences failed), it is **hard-blocked** from approval until a human explicitly acknowledges the anomaly.

```
Draft ─▶ PendingReview ─(human approves)─▶ Approved ─▶ (simulated) Sent
                       └─(critical anomaly)─▶ BLOCKED until human acknowledges
```

**Why we chose it for this project**
Alternative considered: advisory-only warnings (the human *may* notice the anomaly). Rejected — a warning you can click past is theater. A hard block makes the oversight real. What we gave up: a tiny bit of speed, in exchange for trustworthiness — the right trade for customer-facing output.

---

## Part 3 — The Agent Layer

*Its job: turn finished lab results into a customer-ready draft and a clear anomaly report.*

### Deterministic anomaly detection — the checklist, not the oracle

**What it is**
The anomaly detector is a **fixed inspection checklist**, not an AI judgment call. It applies explicit rules ("if the positive control is out of range → critical") the same way every time.

**The problem it solves**
If we asked an LLM "does anything look wrong?", the answer would vary run to run and couldn't be trusted as a safety gate. Safety checks must be predictable and explainable.

**How it works**
1. Read the structured results (expression, binding, Kd, control status, replicate counts).
2. Apply each rule; collect findings tagged critical or warning, each with the evidence that triggered it.
3. Critical findings feed the hard-block in the approval gate (Part 2).

**Why we chose it for this project**
Alternative considered: LLM-based anomaly detection. Rejected for the *gate* (non-deterministic, unexplainable), though the LLM still writes the prose *around* these facts. Splitting "detect" (deterministic) from "describe" (LLM) is the key design decision here.

**Key things to know**
- Rules and thresholds live in one place so a scientist could tune them without touching agent logic.

### EmailDrafter with placeholder substitution — the ghostwriter who leaves blanks

**What it is**
The drafter is a **ghostwriter who writes with numbered blanks.** Claude writes the friendly prose but, instead of typing figures, it leaves typed placeholders (like `{{kd_mean_binder1}}`); the agent then fills each blank with the exact validated number from the real results. The model shapes the sentences; it never sources the figures itself.

**The problem it solves**
LLMs can "hallucinate" plausible-but-wrong numbers. Emailing a customer a made-up binding affinity would be a serious error. The placeholder-substitution approach makes it very hard for a wrong number to slip through — and a deterministic guard rejects any unresolved or unknown placeholder — though it is a strong safeguard, not an absolute mathematical guarantee, which is why the eval guard backs it up.

**How it works**
1. The agent extracts the exact figures and anomaly findings, each under a typed placeholder id.
2. Claude receives the available placeholder ids and a tone instruction, and returns prose containing placeholders (not raw numbers).
3. The agent substitutes each placeholder with its validated numeric string; a guard rejects any unresolved or unknown placeholder — belt and braces.

**Why we chose it for this project**
Alternative considered: let the model read raw results and summarize freely. Rejected — that's exactly where hallucinations enter. What we gave up: a little fluency/flexibility, for correctness we can prove.

**Key things to know**
- Model IDs and parameters are confirmed via the `claude-api` reference at build time, not guessed. Default lean: a current Sonnet-class model for drafting, a strong model for judging.

---

## Part 4 — The Interoperability Layer

*Its job: let a human drive the whole system by talking to Claude — without re-implementing the SDK.*

### MCP server — the universal adapter for AI assistants

**What it is**
MCP (Model Context Protocol) is a **standard wall-socket that lets any AI assistant plug into your tools.** Our MCP server is the adapter that exposes lab actions ("create experiment", "get results") as things Claude can *do*, not just talk about.

**The problem it solves**
Claude on its own can discuss proteins but can't touch Adaptyv's lab. Without a standard interface, you'd hand-wire a bespoke integration for every assistant. MCP is the common plug so it works in Claude Desktop, Claude Code, and beyond.

**How it works**
1. The server declares a set of **tools**, each with a name, description, and typed parameters.
2. Claude reads those descriptions and, when a user asks in plain English, picks a tool and fills the parameters.
3. The server runs the action and returns a result Claude can explain.

**Why we chose it for this project**
It's a hard requirement of the role (TypeScript MCP). The design choice within it: **task-shaped tools, not 25 CRUD wrappers** — the strongest industry warning is that naively wrapping every endpoint produces a technically-working but frustrating server. We expose ~8 tools shaped like real jobs ("create_experiment_with_sequences").

**Key things to know**
- Tool descriptions are written *for the model to read* — they're prompt engineering, not API docs.
- Every parameter is described so Claude fills them correctly.

### The SDK bridge pattern — one brain, two languages

**What it is**
Our SDK is Python; the MCP must be TypeScript; and TypeScript can't directly import Python. The bridge is a **dumbwaiter between two floors**: for each request the TypeScript MCP drops a small JSON note down to a short-lived Python process (`python -m adaptyv --json`), the Python side does the real work via the SDK, and sends a JSON answer back up. No phone line stays open — each call is its own quick trip.

**The problem it solves**
Without it, we'd have to *re-implement* all the lab logic (auth, retries, mock mode, result parsing) a second time in TypeScript — two brains to keep in sync, double the bugs. The bridge keeps the Python SDK as the single source of truth.

**How it works**
1. The MCP receives a tool call from Claude.
2. It **spawns `python -m adaptyv --json <op>`**, passing the request as JSON.
3. The Python process runs the SDK/agent and prints a JSON result (or a typed error), then exits. One codebase owns all the real logic; the MCP is a thin translator.

```
MCP (TS) ──spawn + JSON──▶ python -m adaptyv --json ──▶ adaptyv SDK ──▶ lab
```

**Why we chose it for this project**
Two alternatives were considered. (1) An *auto-spawned FastAPI sidecar* — a long-running local web server the MCP starts and calls over localhost. A Codex review flagged that starting a web server from a stdio MCP hides real complexity: port allocation, a readiness handshake, process cleanup, and version skew. (2) A *separate thin TypeScript client* — simplest to run, but duplicates logic across two languages. The **subprocess bridge** is the middle path: it keeps the Python SDK as the one brain ("wrap once, reuse everywhere") without any server lifecycle to get wrong. What we gave up: a tiny per-call process-startup cost, which is negligible at demo scale.

---

## Part 5 — The Trust & Improvement Layer

*Its job: prove the output is good, and make it get better over time.*

### LLM-as-judge evals — the second marker

**What it is**
A judge is **a second, independent examiner** — a separate LLM whose only job is to score the drafted email against a rubric (accuracy, completeness, tone), the way a second marker grades an essay against criteria.

**The problem it solves**
"The email looks fine" is not a quality guarantee, and quality can silently regress when we tweak a prompt. Evals turn "looks fine" into a measurable score with a pass threshold, so regressions fail loudly.

**How it works**
1. A **golden set** pairs example results with the facts a good email must contain.
2. **Deterministic guards** check the hard rules (no number appears that isn't in the source data; critical anomalies are flagged).
3. The **LLM judge** scores the softer qualities (tone, completeness) against a plain-English rubric; scores below threshold fail.

**Why we chose it for this project**
Alternatives considered: DeepEval (heavier framework) and promptfoo (YAML/CLI). We hand-roll a lightweight judge instead — transparent, dependency-light, and visibly our own work, which matters when the reviewers are the team who'll maintain it. What we gave up: some off-the-shelf metric breadth.

**Key things to know**
- Deterministic guards are the *primary* gate (cheap, reliable); the LLM judge covers what rules can't (does this *read* like a professional update?).

### The three feedback loops — loop engineering

**What it is**
Three cycles that turn a one-shot pipeline into a system that runs continuously and improves itself:
1. **Eval→improve loop** — a *fitness tracker*: score the drafts, see regressions, fix, re-score.
2. **Human-feedback flywheel** — a *spinning wheel that stores energy*: every human edit/rejection (captured in the audit log) becomes a new golden-set case, so real corrections raise the bar for next time.
3. **Autonomous watch loop** — a *night-shift monitor*: the agent polls for newly-finished experiments and queues drafts on its own.

**The problem it solves**
Without loops, the agent is static — it never learns from the corrections humans make, and someone must trigger it by hand. The loops close the gap between "it ran once" and "it operates and improves."

**How it works**
```
watch loop ─▶ agent drafts ─▶ human reviews (HITL) ─▶ correction logged (audit)
     ▲                                                        │
     └──────────────── flywheel promotes correction ──────────┘
                       to the golden set ─▶ eval loop enforces it next run
```

**Why we chose it for this project**
The elegant part: the flywheel *reuses components we already built for other reasons* (the audit log and the eval golden set), so "loop engineering" costs almost nothing extra. We deliberately **skipped** a self-refinement loop (the agent critiquing and rewriting itself repeatedly) — it adds cost and latency for marginal gain when a human reviews everything anyway. Naming a deferred option is itself an architectural signal.

---

## Key Terms Glossary

- **API** — the online doorway software uses to talk to the lab system.
- **OpenAPI spec** — the lab's official, machine-readable description of every API endpoint and data shape.
- **SDK** — a toolkit that wraps an API so software can use it cleanly.
- **pydantic model** — a labelled, type-checked form that validates incoming data.
- **Transport** — the swappable "phone line" the SDK uses (live or mock).
- **Fixture** — a canned example response used for demos and tests.
- **Contract test** — a test proving mock data still matches the real schema.
- **Subprocess bridge** — a short-lived Python process (`python -m adaptyv --json`) the TypeScript MCP spawns per call to reach the Python SDK, exchanging JSON.
- **MCP (Model Context Protocol)** — a standard that lets AI assistants call your tools.
- **Tool (MCP)** — one action Claude can invoke, with a name, description, and typed parameters.
- **Zod** — the TypeScript library that describes and validates tool parameters.
- **Hash / fingerprint** — a short string derived from data; changes if the data changes.
- **Hash chain** — log entries each sealed with the previous entry's hash, making tampering evident.
- **Data lineage** — the record of which exact source numbers fed a given output.
- **Data minimization** — storing only the sensitive data you actually need.
- **Human-in-the-loop (HITL)** — a required human review/approval step before an action completes.
- **Anomaly (critical/warning)** — a rule-detected problem in results; critical ones block sending.
- **Hallucination** — an LLM confidently producing false information (e.g. a made-up number).
- **Fact injection** — giving the model exact figures so it never sources numbers itself.
- **Eval / golden set** — a scored test of output quality against known-good expectations.
- **LLM-as-judge** — using a separate LLM to score another LLM's output against a rubric.
- **Feedback loop / flywheel** — a cycle where usage and review feed back to improve the system.
- **TestPyPI** — the dress-rehearsal version of the public Python package registry.

---

## How to explain this in an interview

**60-second version (corridor):**
"It takes Adaptyv's lab — which today mostly only engineers can drive — and makes it usable by talking to Claude. I built a clean Python SDK over the Foundry API, wrapped it in a TypeScript MCP server so anyone can run experiments and pull results in plain English, and added an agent that drafts the customer result email automatically. Crucially it never sends unreviewed — there's a human sign-off gate, a tamper-evident audit log, and an eval suite that scores the drafts, so it's automation the team can actually trust."

**Technical version (senior engineer):**
"The Python SDK is the single source of truth — hand-written httpx + pydantic v2 modelled from the *raw* OpenAPI spec (discriminated result unions, a pagination envelope, list-vs-detail models), with a Transport protocol so `mock=True` swaps in fixture-backed responses, and a contract test that validates fixtures against the pinned OpenAPI JSON Schema. The TypeScript MCP doesn't re-implement HTTP — it delegates to the SDK via a subprocess JSON bridge (`python -m adaptyv --json`), so logic lives in one place with no server lifecycle to manage. Tools are task-shaped, not 1:1 CRUD. The ExperimentWatcher splits detection (a deterministic, policy-driven rule engine, so the safety gate is explainable) from description (Claude writes prose with typed placeholders that the agent substitutes with validated numbers, so figures can't be invented). Governance is an append-only SQLite audit log (hash-chained in the stretch tier) plus an approval state machine where the agent can't self-approve and critical anomalies hard-block. Quality is deterministic guards as the CI gate, with an LLM-judge and feedback flywheel as reported/stretch layers."

**Business version (executive / regulator):**
"We made an existing capability — the lab's ordering and results system — usable by the whole company through normal conversation, and we automated the drafting of customer result emails. We built in the controls a regulated business needs: a person must approve every customer email, the system blocks anything with a serious data problem until a human signs off, and every action is recorded in a logbook that can't be quietly altered. We only store the minimum sensitive data, and we continuously grade the AI's output so we'd know immediately if quality slipped. The result is faster customer communication with accountability built in, not bolted on."
```
