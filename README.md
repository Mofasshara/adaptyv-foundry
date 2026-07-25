# Adaptyv Foundry SDK + MCP Server + ExperimentWatcher Agent

A typed Python SDK for Adaptyv Bio's Foundry lab API, a TypeScript MCP server so Claude can drive the lab in plain English, and a governed agent that drafts customer-update emails from finished results — with a human sign-off gate and a tamper-evident audit trail so nothing reaches a customer unreviewed.

Built as a take-home for an AI Engineer role at Adaptyv Bio. No live API key was available, so everything below runs against a fixture-backed **mock mode** that is structurally identical in shape to the real API (validated against the vendored OpenAPI spec, not just internal models).

For the "why" behind every component and design decision — written for a non-engineer building toward a technical understanding — see [`LEARNING_GUIDE.md`](LEARNING_GUIDE.md). For the system diagram and end-to-end data flows, see [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md). For the full build history, phase-by-phase, including every design change and why, see [`ROADMAP.md`](ROADMAP.md).

## What this actually does

Adaptyv's customers submit protein sequences and get back binding-affinity and stability measurements. Today, driving that pipeline and writing the results email is a manual, engineer-mediated chore. This project:

1. Wraps the Foundry API in a clean, typed Python SDK (`adaptyv/`) — one client, `mock=True` or `mock=False`, identical shapes either way.
2. Exposes it to Claude Desktop/Code via an MCP server (`mcp/`), so anyone can create experiments, check status, and pull results by asking in plain English.
3. Runs an `ExperimentWatcher` agent that polls for completed results, deterministically flags anomalies (never an LLM's judgment call — a fixed policy), and drafts a plain-English customer update — which a human must review and approve before it's ever "sent." Every draft, review, and anomaly acknowledgement is recorded in a hash-chained, append-only audit log.
4. Backs all of it with an offline eval suite (`evals/`) that gates on deterministic guards — not vibes — so a prompt or code change that reintroduces a defect fails loudly before it ships.

## Quickstart

Requires Python 3.11+ and Node.js 18+.

```bash
# Python SDK + CLI
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"

# Try it — everything below runs with no API key, against fixtures
adaptyv experiments list
adaptyv results get aaaaaaaa-0000-0000-0000-000000000001

# Run the full test suite
make test        # 170 tests

# Run the offline eval suite (deterministic guards, zero LLM calls, zero cost)
make eval         # 3/3 golden cases

# MCP server (TypeScript)
cd mcp && npm install && npm test    # 16 tests
npm run build
```

Point Claude Desktop's MCP config at `mcp/dist/index.js` to drive the lab conversationally (see `docs/ARCHITECTURE.md` for the exact tool list and what each does).

### Watching for new results and drafting updates

```bash
# One polling cycle, mock data, stub drafter (no Anthropic key needed)
adaptyv watch --once

# Review what it drafted
adaptyv review list
adaptyv review show <draft_id>

# A human approves (or rejects) — the agent can never do this itself
adaptyv review approve <draft_id> --by "alice@adaptyvbio.com"

# Verify the audit trail hasn't been tampered with
adaptyv audit verify
```

If a result trips a **critical** anomaly (e.g. all sequences failed, or the positive control is out of policy range), `review approve` is hard-blocked until a human runs `review ack` — there's no code path that lets a critical anomaly reach a customer silently.

To use real Claude-drafted emails instead of the deterministic stub, set `ANTHROPIC_API_KEY` and pass `mock_llm=false` where the bridge/MCP tool expose it (see `docs/ARCHITECTURE.md`) — this is the only part of the system that costs money or calls a live model; everything else, including the entire eval suite, is free and offline by design.

## Project layout

```
adaptyv/              Python SDK — the single source of truth
├── models.py          typed request/response models, schema-faithful to the real OpenAPI spec
├── transport.py       MockTransport (fixtures) / live_transport.py (real httpx client)
├── client.py          AdaptyvClient(mock=True|False) — same shape either way
├── resources/         experiments, sequences, targets, results
├── agents/            AnomalyDetector, EmailDrafter, Watcher (the governed agent)
├── governance/        ApprovalStore (HITL state machine), AuditLog (hash-chained)
├── bridge.py           the MCP↔SDK subprocess JSON bridge (`python -m adaptyv --json`)
└── cli.py              the `adaptyv` command-line tool

mcp/                  TypeScript MCP server — 8 task-shaped tools over stdio
evals/                Offline eval suite: golden set, deterministic guards, eval→improve
                      loop, human-feedback flywheel
tests/                170 tests covering every module above
docs/                 Architecture, design specs, phase-by-phase implementation plans
```

## Honest scope and limitations

This is a take-home, not a production system, and it's been reviewed hard (three rounds of external code review, each fixing real defects the previous round missed or introduced — the full history is in `ROADMAP.md`'s Change Log, including what was found and how it was fixed). What's still explicitly out of scope, by design:

- **No live LLM-judge eval.** The eval suite gates on deterministic guards only (fact-grounding, anomaly-rule matching, HITL hard-block enforcement) — a rubric-scored LLM judge was scoped as a stretch goal and deliberately not built, since it requires live, costed Anthropic API calls that shouldn't happen by default in an offline test suite.
- **Concurrency is single-connection.** The governance store (`ApprovalStore`, `AuditLog`) is safe for one process/connection at a time; it does not yet handle two reviewers or two watcher processes racing on the same sqlite connection from different processes.
- **The subprocess bridge trusts its caller.** `python -m adaptyv --json` is meant to be spawned by the bundled MCP server, not exposed to untrusted input directly; the MCP tool that drafts customer updates lets the calling model choose the governance database path and whether to call a live LLM, which is a reasonable tool-surface choice for a local, single-user desktop tool but would need tightening before any multi-tenant use.
- **`MockTransport` doesn't implement pagination/filtering.** It always returns the full fixture set; only `LiveTransport` genuinely paginates against a real server.
- A handful of smaller, explicitly logged items (live-transport network-error mapping, a few incomplete response models) are tracked in `ROADMAP.md` rather than silently left unmentioned.

## Testing philosophy

Every module was built test-first. `make test` runs all 170 Python tests; `make eval` runs the offline agent-output eval suite; `cd mcp && npm test` runs the 16 TypeScript tests. All three are fully offline — no network calls, no API key, no cost — which is also true of every CI-relevant check in this repo.
