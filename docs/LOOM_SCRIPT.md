# Loom Demo Script (~2 minutes)

Record with a terminal and Claude Desktop (with the MCP server configured) both visible. Everything below runs against mock data — no API key needed, nothing costs money.

## Setup before recording

```bash
cd adaptyv-foundry
. .venv/bin/activate
rm -f adaptyv_governance.db   # start from a clean governance db for the demo
```

Have Claude Desktop open with the MCP server (`mcp/dist/index.js`) already configured, in a second window/tab.

---

## Beat 1 — The problem (0:00–0:15)

**Say:** "Adaptyv's Foundry API is powerful, but today only engineers can drive it, and writing customer result emails is a manual chore. This is a typed Python SDK, a TypeScript MCP server so you can drive the lab by talking to Claude, and an agent that drafts those emails — with a human always in the loop before anything goes out."

## Beat 2 — Driving the lab through Claude (0:15–0:45)

Switch to Claude Desktop. Type something like:

> "List the experiments in the Adaptyv lab and tell me which ones are done."

Let Claude call `list_experiments` and summarize the result. Then:

> "Get me the results for the Anti-IL6 binder panel."

Let it call `get_results` and describe the binding data in plain English.

**Say (while it responds):** "Claude is calling the real SDK through an MCP server — 8 task-shaped tools, not a raw API wrapper. Under the hood, each call spawns the Python SDK as a subprocess, so there's exactly one implementation of the lab logic, in Python, and the TypeScript side never re-implements any of it."

## Beat 3 — The governed agent + human sign-off (0:45–1:30)

Switch to the terminal:

```bash
adaptyv watch --once
```

**Say:** "This polls for completed results and drafts a customer update for each one — but nothing is ever sent automatically."

```bash
adaptyv review list
```

You'll see 3 drafts. The draft IDs (the long UUID at the start of each line) are randomly generated fresh every run — they will be different every time you do this, including on your actual recording take. **Do not hardcode or memorize a specific ID** — always read it live from your own terminal output.

Two of the three will show `⚠CRITICAL`. Pick **either one** and copy its draft ID for the next few commands — but note which underlying anomaly it is, since that changes what you say next:
- If the row's experiment is `33333333-3333-3333-3333-333333333333` → the anomaly is **all sequences failed** (no measurable binding at all).
- If the row's experiment is `44444444-4444-4444-4444-444444444444` → the anomaly is **positive control out of range**.

```bash
adaptyv review show <draft_id>
```

(Replace `<draft_id>` with the UUID you just copied.)

**Say (generic, works for either):** "This one has a critical anomaly flagged automatically — [say either "no measurable binding on any sequence" or "the positive control came back outside its expected range," matching whichever one is actually on your screen]. Watch what happens if I try to approve it anyway."

```bash
adaptyv review approve <draft_id> --by you@adaptyvbio.com
```

**Say:** "Hard-blocked. The agent cannot approve its own work, and a critical anomaly cannot be waved through — a human has to explicitly acknowledge it first."

**Say:** "So I acknowledge it — that's a human explicitly taking responsibility for having seen the anomaly, recorded under my name — and only then can I approve it."

```bash
adaptyv review ack <draft_id> --by you@adaptyvbio.com
adaptyv review approve <draft_id> --by you@adaptyvbio.com
```

(No quotes around the email — Typer only needs quotes around a value if it contains a space, and an email address doesn't, so leaving them off avoids any copy-paste/smart-quote trouble live.)

## Beat 4 — Trust: the audit trail and eval suite (1:30–1:50)

```bash
adaptyv audit verify
```

**Say:** "Every one of those actions — the draft, the block, the acknowledgement, the approval — is in a hash-chained audit log. If anyone edited an old entry, this command would catch it."

```bash
make eval
```

**Say:** "And this is the eval suite — it runs the real drafting pipeline against known results and mechanically checks that no hallucinated number, no leftover placeholder, and no broken safety gate ever slips through. Fully offline, zero cost, and it's what actually caught real bugs across three rounds of review while building this."

## Beat 5 — Close (1:50–2:00)

**Say:** "Typed SDK, conversational MCP interface, and a governed agent that's fast to draft but never fast to send — that's the whole pitch."

---

## Notes for whoever records this

- If a take runs long, Beat 3 is the one to compress — the hard-block moment is the most important single beat to keep.
- The exact draft IDs will differ every time `adaptyv watch --once` is re-run against a fresh db — read the real one off `review list`'s output live rather than hardcoding it.
- `docs/ARCHITECTURE.md` has the full tool list and data-flow diagrams if you want to show a slide instead of narrating the MCP call.
