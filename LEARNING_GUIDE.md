# Learning Guide — Adaptyv Foundry SDK + MCP + Lab Ops Agent

> A living explainer for every concept, tool, and decision in this project.
> Written in two layers: plain-English analogy first, technical mechanism second.
> Updated as we build. Last updated: 2026-07-26 (post-implementation — reflects
> what was actually built across 5 phases and 3 rounds of external review, not
> the original pre-implementation design; see `ROADMAP.md`'s Change Log for
> every place the two diverge and why).

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

### Packaging — shipping the toolkit honestly

**What it is**
Packaging turns our folder of code into an installable product (`pip install ...`). `pyproject.toml` already declares everything needed: package name (`adaptyv-foundry-sdk`, deliberately not `adaptyvbio` — see below), version, dependencies, and the `adaptyv` CLI entry point, built with `hatchling`.

**The problem it solves**
"It works on my machine" isn't a deliverable. A reviewer needs to install it the same way they'd install any real library (`pip install -e ".[dev]"`), not clone-and-hope.

**How it works**
1. `pyproject.toml` declares the package name, version, dependencies, and CLI entry point.
2. `pip install -e .` (editable install) is enough to make the `adaptyv` command and the `adaptyv` package importable — this is what the README's quickstart actually uses and what was verified before writing it.
3. Publishing to **TestPyPI** (the dress-rehearsal version of the real Python package registry) is the natural next step for making the package installable by a stranger with no local checkout at all — labeled a stretch goal, not attempted in this build, since publishing anything (even to a test registry) is an action with an external, visible side effect that should be a deliberate choice, not something done by default.

**Why we chose it for this project**
Publishing under the real name `adaptyvbio` on the real PyPI registry was rejected outright — that would be squatting a brand that belongs to the company being interviewed with. A local editable install is the honest, no-side-effects baseline; TestPyPI publication remains available as a follow-up if wanted.

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

### EmailDrafter with deny-by-default substitution — the ghostwriter who leaves blanks, watched by a bouncer

**What it is**
The drafter is a **ghostwriter who writes with numbered blanks, checked by a bouncer who rejects anyone who tries to sneak a number past the door list.** Claude writes the friendly prose but, instead of typing figures, it leaves typed placeholders (opaque ones like `{{kd_1}}`, not name-derived); the agent fills each blank with the exact validated number from the real results. Separately — and this is the part that took three attempts to get right — **any digit that appears anywhere outside a placeholder is rejected outright**, before the agent even tries to substitute anything. The model never sources a figure itself, and it can't sneak one in as plain prose either.

**The problem it solves**
LLMs can "hallucinate" plausible-but-wrong numbers. Emailing a customer a made-up binding affinity would be a serious error. The first two attempts at this guard were themselves not fully correct — see "Deny-by-default vs. detection" below for exactly what was wrong and why the current version is different in kind, not just in degree.

**How it works**
1. The agent extracts the exact figures under opaque placeholder ids (`kd_1`, `kd_2`, ...) — a plain counter, not derived from sequence names, so there's nothing for two entries to collide over.
2. Anomaly findings (which legitimately contain numbers the drafter is told to echo verbatim, like "0 replicates, policy requires 2") are *also* rewritten with their own numbers replaced by placeholders before the prompt is ever built — so "copy this text exactly" can never reintroduce a raw number.
3. Claude receives the available placeholder ids and a tone instruction, and returns prose that should only reference figures via `{{token}}`.
4. Before substituting anything, the agent strips out every well-formed placeholder and checks whether any digit remains in what's left. If one does — a number typed directly as prose — the whole draft is rejected, no exceptions, even if that number happens to be correct.
5. After substitution, any leftover `{` or `}` character (an empty, unclosed, or malformed placeholder) is also rejected.

**Why we chose it for this project**
Alternative considered: let the model read raw results and summarize freely. Rejected — that's exactly where hallucinations enter. What we gave up: a little fluency/flexibility, for correctness we can prove.

**Key things to know**
- Model IDs and parameters are confirmed via the `claude-api` reference at build time, not guessed.
- The offline eval suite does **not** keep a second, separate implementation of this check — it runs the real `EmailDrafter.draft()` (against a deterministic fake client, so it stays free and offline) and treats any rejection as a failed test case. There is exactly one implementation of "no raw numbers get through," not two that could drift apart.

### Deny-by-default vs. detection — the lesson three review rounds taught

**What it is**
Two different shapes a safety check can take. A **detection** check is a bouncer with a list of known troublemakers' faces — it stops everyone it recognizes, and lets through anyone it doesn't. A **deny-by-default (construction)** check is a bouncer with a guest list — nobody gets in unless their name is *on* the list, recognized or not.

**The problem it solves**
The first version of this project's number-guard was detection-based: a regex looking for placeholder-*shaped* text, and later a check asking "does this number appear somewhere in the known facts?" Both looked reasonable and both were wrong, in the same way: a detection rule can only catch the specific patterns its author thought to write down. An external review found the exact gap twice — a model that typed a *correct* number as plain prose (no placeholder at all) sailed straight through the "is this number grounded" check, because the check only asked "does a matching number exist somewhere," not "did this number actually come through the verified path."

**How it works**
```
Detection (round 1 & 2):  is this thing on my list of bad things?  → miss anything not on the list
Construction (final):     did this thing come through my one allowed path?  → nothing else can get through
```
Concretely: instead of asking "is this number one I recognize as a real fact" (detection), the final version asks "did this number arrive via a `{{fact_id}}` token I resolved myself" (construction) — and rejects every other digit, regardless of whether it happens to be numerically correct.

**Why we chose it for this project**
This is a general pattern worth recognizing anywhere a guarantee is being enforced against a generative model's output (prompt-injection filtering, PII redaction, content moderation) — not specific to email drafting. Detection-based checks feel productive because they visibly catch real examples during testing, which is exactly what makes them dangerous: they pass code review and still have gaps, because "did we enumerate every bad pattern" is unanswerable in the general case. Construction-based checks are less flexible to write (they require redesigning *how* the allowed content is produced, not just adding a filter afterward) but close the whole class of problem at once instead of one instance at a time.

**Key things to know**
- The tell that a check is detection-based, in code: it's built as "scan the output for X, reject if found" rather than "the output can only contain X because of how it was assembled."
- If a review finds a second instance of the same class of bug in something you already "fixed" once, that's the signal to stop patching and ask whether the design is detection or construction — not to write a third patch.

### Idempotency — the "did I already do this" check

**What it is**
Idempotency is **a hotel check-in desk that remembers who already has a room key.** If the same guest tries to check in twice — because they forgot they already did, or the front desk's computer crashed mid-check-in and they're trying again — the desk recognizes them and doesn't hand out a second room.

**The problem it solves**
The Watcher polls for finished results and drafts an email for each one. If it's run twice — a scheduled retry, a restart after a crash, a second `adaptyv watch --once` — a naive implementation would draft (and eventually send) the *same* customer update twice. Worse, a crash at exactly the wrong moment (draft written, but the "already handled" marker not yet saved) could silently produce a duplicate on the very next run.

**How it works**
1. Every result gets a durable key: `experiment_id:result_id:drafter_model`, stored in a `watcher_processed` sqlite table.
2. Before drafting anything, the Watcher checks whether that key already has a row. If it does, the result is skipped — already handled.
3. The tricky part: the marker write has to happen in the **same database transaction** as the draft and its audit entry, not as a separate step afterward — otherwise a crash between "draft saved" and "marker saved" leaves a draft with no marker, and the next run duplicates it. This project's real history: an earlier version wrote the marker as a separate, later commit, outside the code path that isolates a single result's failure from crashing the whole batch — a review caught both problems (non-atomic write, and a failure there could crash every other result too) and fixed them together with one change: the marker write became a hook invoked *inside* the same transaction as the draft, so all three writes commit — or roll back — as one unit.

**Why we chose it for this project**
A polling agent that isn't idempotent is unsafe to actually run on a schedule or retry after any failure — which defeats the point of "autonomous." The durable-key-in-the-same-transaction approach was chosen over "just don't crash" (unrealistic) or "de-duplicate on the receiving end" (there is no receiving end to de-duplicate against — the email really would go out twice).

**Key things to know**
- "Idempotent" doesn't mean "can't fail" — it means "failing and retrying produces the same end state as succeeding once." That's a much easier, much more achievable bar.
- The same pattern — a durable key, written atomically with the thing it protects — is worth reaching for anywhere a process might restart, retry, or run twice: webhook handlers, payment processing, scheduled jobs.

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

### Deterministic-guard evals — the checklist inspector, not a second marker

**What it is**
The eval suite is a **checklist inspector**, not a second examiner: it runs the real drafting pipeline against a set of known results and mechanically checks hard rules — not a subjective read of tone or fluency.

**The problem it solves**
"The email looks fine" is not a quality guarantee, and a code or prompt change could silently reintroduce a defect (a leftover placeholder, an ungrounded number, a hard-block that stopped blocking). `make eval` turns "looks fine" into a pass/fail check that fails loudly, immediately, and for free — no API key, no cost, no network call.

**How it works**
1. A **golden set** (`evals/golden_set.py`) pairs real mock-fixture experiments with the exact facts and critical-anomaly rules a correct run over them must produce.
2. `evals/run_eval.py` runs the *real* `EmailDrafter.draft()` against those experiments, using a deterministic fake Anthropic client (`evals/fake_llm.py`) so the real substitution/rejection logic is genuinely exercised with zero network calls.
3. Remaining guards (`evals/guards.py`) check what the draft pipeline can't check about itself: does the detected critical-anomaly set match what's expected, are the expected fact keys present, does a critical anomaly genuinely hard-block approval when it's supposed to.
4. A **human-feedback flywheel** (`evals/flywheel.py`) promotes real corrected/rejected drafts into new golden-set cases, so an actual mistake a reviewer caught becomes a permanent regression test.

**Why we chose it for this project**
A rubric-scored **LLM-as-judge** tier (a second model scoring tone/completeness against a plain-English rubric) was considered and scoped as an explicit stretch goal — deliberately **not built**, because it requires live, costed Anthropic API calls on every eval run, which shouldn't happen by default in a suite that's otherwise free and instant. The deterministic-only suite is the honest, always-on gate; an LLM judge remains a documented, available follow-up, not a silently-dropped promise.

**Key things to know**
- Deterministic guards are the *only* gate here, not a warm-up act for a judge — there is no soft, subjective scoring layer in this build.
- The eval suite deliberately does not duplicate `EmailDrafter`'s own hallucination-prevention checks (see "Deny-by-default vs. detection" above) — it runs the real code and treats any exception as a failed case, so there's exactly one implementation of that guarantee, not two that could drift.

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
- **LLM-as-judge** — using a separate LLM to score another LLM's output against a rubric; considered for this project, deliberately not built (costed, non-deterministic; see Part 5).
- **Feedback loop / flywheel** — a cycle where usage and review feed back to improve the system.
- **TestPyPI** — the dress-rehearsal version of the public Python package registry; a follow-up option here, not yet done.
- **Deny-by-default / construction check** — a safety rule that blocks everything except what came through one verified path, vs. a **detection check** that blocks only recognized bad patterns.
- **Idempotency** — the property that retrying an operation produces the same end state as running it once, via a durable key checked (and written) atomically with the operation it protects.
- **Opaque ID** — an identifier that carries no information about its source (a plain counter, e.g. `kd_1`), chosen specifically so there's nothing about it that could collide or leak.

---

## How to explain this in an interview

**60-second version (corridor):**
"It takes Adaptyv's lab — which today mostly only engineers can drive — and makes it usable by talking to Claude. I built a clean Python SDK over the Foundry API, wrapped it in a TypeScript MCP server so anyone can run experiments and pull results in plain English, and added an agent that drafts the customer result email automatically. Crucially it never sends unreviewed — there's a human sign-off gate, a tamper-evident audit log, and a deterministic eval suite that fails loudly if a code change reintroduces a defect, so it's automation the team can actually trust."

**Technical version (senior engineer):**
"The Python SDK is the single source of truth — hand-written httpx + pydantic v2 modelled from the *raw* OpenAPI spec (discriminated result unions, a pagination envelope, a model validator enforcing the real create-experiment assay matrix), with a Transport protocol so `mock=True` swaps in fixture-backed responses, and a contract test that validates fixtures against the pinned OpenAPI JSON Schema. The TypeScript MCP doesn't re-implement HTTP — it delegates to the SDK via a subprocess JSON bridge (`python -m adaptyv --json`), so logic lives in one place with no server lifecycle to manage. Tools are task-shaped, not 1:1 CRUD. The ExperimentWatcher splits detection (a deterministic, policy-driven rule engine, so the safety gate is explainable) from description (Claude writes prose with opaque placeholders; the drafter rejects any raw digit that didn't come through a resolved placeholder — deny-by-default, not a pattern-matching filter). Governance is a hash-chained, append-only SQLite audit log plus an approval state machine where the agent can't self-approve and critical anomalies hard-block, with the idempotency marker committed atomically with the draft and its audit entry. Quality is deterministic guards as the sole CI gate — no LLM-judge tier, by design, since that would need live costed API calls in a suite that should otherwise be free and instant — plus a human-feedback flywheel and an autonomous watch loop. This went through three rounds of external review; the most interesting fix wasn't a bug, it was redesigning the hallucination guard from a detection check (does this number match something I recognize) to a construction check (did this number come through the one verified path) after the detection version kept having gaps."

**Business version (executive / regulator):**
"We made an existing capability — the lab's ordering and results system — usable by the whole company through normal conversation, and we automated the drafting of customer result emails. We built in the controls a regulated business needs: a person must approve every customer email, the system blocks anything with a serious data problem until a human signs off, and every action is recorded in a logbook that can't be quietly altered. We only store the minimum sensitive data, and we mechanically check the AI's output against hard rules on every change, so we'd know immediately if a bug let something wrong through. The result is faster customer communication with accountability built in, not bolted on."
```
