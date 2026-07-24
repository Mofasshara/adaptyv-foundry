# Phase 4 — Subprocess Bridge + TypeScript MCP Server — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let Claude Desktop/Code drive the lab in natural language. A Python subprocess
bridge (`python -m adaptyv --json`) exposes the SDK + agent as a JSON request/response
protocol on stdin/stdout; a TypeScript MCP server spawns that bridge per call and
exposes ~8 curated, task-shaped tools (not 1:1 CRUD wrappers) over stdio to any MCP
client.

**Architecture:** `adaptyv/bridge.py` + `adaptyv/__main__.py` (Python) add a pure
dispatch function `handle_request(request: dict) -> dict` and a thin stdin/stdout
entrypoint — no new Python dependencies, reuses every Phase 1–3 component untouched.
`mcp/` (new TypeScript project) has a dependency-injectable `BridgeClient` that spawns
the bridge per call (verified against the actual `@modelcontextprotocol/sdk` v1.29.0
shipped type definitions and example code — see the plan's Global Constraints), and
~8 tool factory functions, each taking a `BridgeClient` and returning
`{name, config, handler}` ready for `server.registerTool(...)`.

**Tech Stack:** Python 3.11+ (bridge, stdlib `json`/`sys` only), Node.js ≥18 + TypeScript
5.6+, `@modelcontextprotocol/sdk` 1.29.0, `zod` (peer dep, `^3.25 || ^4.0`), `tsx` (dev,
runs `.ts` tests directly via Node's built-in test runner).

## Global Constraints

- **Python side:** 3.11+, sync only, stdlib only (`json`, `sys`) — no new runtime deps.
  Work inside the repo-local venv (`. .venv/bin/activate`); use `python3 -m pytest`.
- **TypeScript side:** Node ≥18 (repo has v25.2.1). `"type": "module"` (ESM) throughout.
  Install with `npm install` inside `mcp/`. Use `node --import tsx --test` for tests
  (Node's built-in test runner + `node:assert`, no Jest/Vitest — keeps deps minimal).
- **Verified MCP SDK API (do not deviate — confirmed against the real npm package
  `@modelcontextprotocol/sdk@1.29.0`'s shipped `.d.ts` files and a real example server,
  not a fetched summary):**
  - `npm install @modelcontextprotocol/sdk zod`
  - `import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js"`
  - `import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js"`
  - `new McpServer({ name, version }, options?)`
  - `server.registerTool(name: string, config: { description?: string, inputSchema?: <raw
    shape object of zod schemas, e.g. { text: z.string() }, NOT z.object({...}) },
    handler: (args, extra?) => Promise<{ content: [{type:"text", text:string}], isError?:
    boolean }>) : RegisteredTool`
  - `await server.connect(transport)`
  - Do **not** use `@modelcontextprotocol/server` (a different, beta-only, pre-release
    package — confirmed via npm registry to be unrelated/immature; not what this
    project targets).
- The bridge signals success/failure via a JSON envelope (`{"ok": true/false, ...}`),
  **not** via process exit code — simpler for the TS side to parse uniformly.
- `BridgeClient` in TypeScript takes an injectable spawn function so tests never spawn a
  real process except one clearly-labeled real end-to-end smoke test.
- Bridge/tool defaults are credential-free: every op defaults `mock: true`;
  `draft_customer_update` defaults `mock_llm: true` (a deterministic stub drafter, no
  Anthropic API key required) — matching the project's "runs with zero credentials"
  principle.
- Tools are task-shaped (≈8 total), each with a model-facing `description` — not a
  1:1 wrapper per SDK endpoint.
- TDD: failing test first (fails for the real reason), then minimal code, green, commit.
- Commit messages exactly as written below; **NO `Co-Authored-By`/`Generated with`
  trailer**. Commit only each task's own files with explicit `git add <paths>` (never
  `-A`/`-am`); do **not** touch `ROADMAP.md`/docs in task commits.
- End every Python-touching task with `python3 -m pytest -q` fully green. End every
  TypeScript-touching task with `npx tsc --noEmit` (type-check) and
  `npm test` both green, output pristine.

---

### Task 1: Python subprocess bridge (`python -m adaptyv --json`)

**Files:**
- Create: `adaptyv/bridge.py`
- Create: `adaptyv/__main__.py`
- Test: `tests/test_bridge.py`

**Interfaces:**
- Produces `adaptyv.bridge.handle_request(request: dict) -> dict` — pure (given a
  request dict, returns a response dict; no stdin/stdout I/O itself, so it's directly
  unit-testable).
- Response envelope: `{"ok": True, "result": <json-serializable>}` on success,
  `{"ok": False, "error": {"type": "<ExceptionClassName>", "message": "<str>"}}` on
  failure.
- Ops (dispatch table, each `(params: dict) -> Any`): `list_experiments`,
  `get_experiment_status`, `create_experiment_with_sequences`, `add_sequences`,
  `search_targets`, `estimate_cost`, `get_results`, `draft_customer_update`.
- `python -m adaptyv --json` reads one JSON request from stdin, writes one JSON
  response to stdout, always exits 0 (the `"ok"` field signals success/failure).

- [ ] **Step 1: Write the failing test** — `tests/test_bridge.py`:
```python
import json
import subprocess
import sys

from adaptyv.bridge import handle_request


def test_unknown_op_returns_structured_error():
    resp = handle_request({"op": "not_a_real_op", "params": {}})
    assert resp["ok"] is False
    assert resp["error"]["type"] == "BridgeError"


def test_list_experiments_mock_default():
    resp = handle_request({"op": "list_experiments", "params": {}})
    assert resp["ok"] is True
    codes = {e["code"] for e in resp["result"]}
    assert "EXP-1001" in codes


def test_get_experiment_status():
    resp = handle_request({"op": "get_experiment_status",
                           "params": {"experiment_id": "11111111-1111-1111-1111-111111111111"}})
    assert resp["ok"] is True
    assert resp["result"]["code"] == "EXP-1001"


def test_get_experiment_status_unknown_id_maps_to_adaptyv_error():
    resp = handle_request({"op": "get_experiment_status",
                           "params": {"experiment_id": "00000000-0000-0000-0000-0000000000ff"}})
    assert resp["ok"] is False
    assert resp["error"]["type"] == "NotFoundError"


def test_get_results():
    resp = handle_request({"op": "get_results",
                           "params": {"experiment_id": "11111111-1111-1111-1111-111111111111"}})
    assert resp["ok"] is True
    assert resp["result"][0]["summary"][0]["result_type"] == "affinity"


def test_create_experiment_with_sequences():
    resp = handle_request({"op": "create_experiment_with_sequences", "params": {
        "name": "MCP test run", "experiment_type": "affinity",
        "sequences": [{"aa_string": "MKAA", "name": "binder-x"}]}})
    assert resp["ok"] is True
    assert resp["result"]["experiment_id"]


def test_search_targets():
    resp = handle_request({"op": "search_targets", "params": {"search": "IL"}})
    assert resp["ok"] is True and resp["result"]


def test_estimate_cost():
    resp = handle_request({"op": "estimate_cost", "params": {
        "experiment_type": "affinity",
        "sequences": [{"aa_string": "MKAA"}]}})
    assert resp["ok"] is True


def test_add_sequences():
    resp = handle_request({"op": "add_sequences", "params": {
        "experiment_code": "EXP-1001", "sequences": [{"aa_string": "MKAA"}]}})
    assert resp["ok"] is True and resp["result"]["added_count"] == 1


def test_draft_customer_update_uses_stub_drafter_by_default(tmp_path):
    resp = handle_request({"op": "draft_customer_update", "params": {
        "experiment_id": "11111111-1111-1111-1111-111111111111",
        "db": str(tmp_path / "gov.db")}})
    assert resp["ok"] is True
    assert resp["result"]["status"] == "pending_review"


def test_missing_required_param_is_a_structured_bridge_error():
    resp = handle_request({"op": "get_experiment_status", "params": {}})
    assert resp["ok"] is False
    assert resp["error"]["type"] == "BridgeError"


def test_cli_entrypoint_end_to_end():
    proc = subprocess.run(
        [sys.executable, "-m", "adaptyv", "--json"],
        input=json.dumps({"op": "list_experiments", "params": {}}),
        capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0
    resp = json.loads(proc.stdout)
    assert resp["ok"] is True and resp["result"]
```

- [ ] **Step 2: Run** `python3 -m pytest tests/test_bridge.py -q` → FAIL
  (`ModuleNotFoundError: No module named 'adaptyv.bridge'`).

- [ ] **Step 3: Implement** — `adaptyv/bridge.py`:
```python
from __future__ import annotations

from typing import Any, Callable

from adaptyv import AdaptyvClient
from adaptyv.agents.anomaly import AnomalyDetector
from adaptyv.agents.email import EmailDraftSchema, EmailDrafter
from adaptyv.agents.policy import DEFAULT_POLICY
from adaptyv.agents.watcher import Watcher
from adaptyv.errors import AdaptyvError
from adaptyv.governance.approval import ApprovalStore
from adaptyv.governance.audit import AuditLog
from adaptyv.governance.db import connect
from adaptyv.models import CostEstimateRequest, CreateExpRequest, ExperimentSpec, SequenceAddRequest, SequenceEntry


class BridgeError(AdaptyvError):
    """Bridge-level error: unknown op or malformed params (not an SDK/API error)."""


def _client(params: dict) -> AdaptyvClient:
    return AdaptyvClient(mock=params.get("mock", True))


def _sequence_entries(raw: list[dict]) -> list[SequenceEntry]:
    return [SequenceEntry(aa_string=s["aa_string"], name=s.get("name")) for s in raw]


def _op_list_experiments(params: dict) -> Any:
    client = _client(params)
    exps = client.experiments.list(search=params.get("search"), filter=params.get("filter"),
                                   sort=params.get("sort"), limit=params.get("limit"),
                                   offset=params.get("offset"))
    return [e.model_dump(mode="json") for e in exps]


def _op_get_experiment_status(params: dict) -> Any:
    client = _client(params)
    exp = client.experiments.get(params["experiment_id"])
    return exp.model_dump(mode="json")


def _op_create_experiment_with_sequences(params: dict) -> Any:
    client = _client(params)
    spec = ExperimentSpec(experiment_type=params["experiment_type"],
                          sequences=_sequence_entries(params.get("sequences", [])),
                          target_id=params.get("target_id"))
    request = CreateExpRequest(name=params["name"], experiment_spec=spec,
                               skip_draft=params.get("skip_draft"))
    return client.experiments.create(request).model_dump(mode="json")


def _op_add_sequences(params: dict) -> Any:
    client = _client(params)
    request = SequenceAddRequest(experiment_code=params["experiment_code"],
                                 sequences=_sequence_entries(params.get("sequences", [])))
    return client.sequences.add(request).model_dump(mode="json")


def _op_search_targets(params: dict) -> Any:
    client = _client(params)
    targets = client.targets.list(search=params.get("search"),
                                  selfservice_only=params.get("selfservice_only"),
                                  detailed=params.get("detailed"))
    return [t.model_dump(mode="json") for t in targets]


def _op_estimate_cost(params: dict) -> Any:
    client = _client(params)
    spec = ExperimentSpec(experiment_type=params["experiment_type"],
                          sequences=_sequence_entries(params.get("sequences", [])),
                          target_id=params.get("target_id"))
    return client.experiments.cost_estimate(CostEstimateRequest(experiment_spec=spec)).model_dump(mode="json")


def _op_get_results(params: dict) -> Any:
    client = _client(params)
    results = client.experiments.results(params["experiment_id"])
    return [r.model_dump(mode="json") for r in results]


class _StubDrafter:
    """Zero-credential drafter for the demo/default path: no Claude call."""
    model = "stub-drafter"

    def draft(self, result, findings) -> EmailDraftSchema:
        lines = [f"Results are in for {result.title}."]
        for f in findings:
            lines.append(f"[{f.severity.value.upper()}] {f.rule}: {f.evidence}")
        if not findings:
            lines.append("No anomalies detected.")
        return EmailDraftSchema(subject=f"Update: {result.title}", body="\n".join(lines))


def _op_draft_customer_update(params: dict) -> Any:
    client = _client(params)
    conn = connect(params.get("db", "adaptyv_governance.db"))
    store = ApprovalStore(conn, AuditLog(conn))
    if params.get("mock_llm", True):
        drafter = _StubDrafter()
    else:
        import anthropic
        drafter = EmailDrafter(client=anthropic.Anthropic())
    watcher = Watcher(client, AnomalyDetector(DEFAULT_POLICY), drafter, store, conn)
    experiment_id = params["experiment_id"]
    drafts = watcher.run(experiment_ids=[experiment_id])
    if drafts:
        draft = drafts[0]
    else:
        existing = [d for d in store.list() if d.experiment_id == experiment_id]
        if not existing:
            raise BridgeError(f"no results available yet for experiment {experiment_id}")
        draft = sorted(existing, key=lambda d: d.created_at)[-1]
    return draft.model_dump(mode="json")


_OPS: dict[str, Callable[[dict], Any]] = {
    "list_experiments": _op_list_experiments,
    "get_experiment_status": _op_get_experiment_status,
    "create_experiment_with_sequences": _op_create_experiment_with_sequences,
    "add_sequences": _op_add_sequences,
    "search_targets": _op_search_targets,
    "estimate_cost": _op_estimate_cost,
    "get_results": _op_get_results,
    "draft_customer_update": _op_draft_customer_update,
}


def handle_request(request: dict) -> dict:
    op = request.get("op")
    params = request.get("params", {})
    if op not in _OPS:
        return {"ok": False, "error": {"type": "BridgeError", "message": f"unknown op '{op}'"}}
    try:
        return {"ok": True, "result": _OPS[op](params)}
    except AdaptyvError as exc:
        return {"ok": False, "error": {"type": type(exc).__name__, "message": exc.message}}
    except KeyError as exc:
        return {"ok": False, "error": {"type": "BridgeError", "message": f"missing required param: {exc}"}}
    except (TypeError, ValueError) as exc:
        return {"ok": False, "error": {"type": "BridgeError", "message": f"invalid params: {exc}"}}
```

- [ ] **Step 4: Implement the entrypoint** — `adaptyv/__main__.py`:
```python
from __future__ import annotations

import json
import sys

from adaptyv.bridge import handle_request


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] != "--json":
        print(json.dumps({"ok": False, "error": {
            "type": "BridgeError",
            "message": "usage: python -m adaptyv --json  (reads one JSON request from stdin)"}}))
        sys.exit(1)
    raw = sys.stdin.read()
    try:
        request = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "error": {"type": "BridgeError",
                                                  "message": f"invalid JSON on stdin: {exc}"}}))
        return
    print(json.dumps(handle_request(request)))


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run** `python3 -m pytest -q` → PASS (all prior + new).
- [ ] **Step 6: Commit**
```bash
git add adaptyv/bridge.py adaptyv/__main__.py tests/test_bridge.py
git commit -m "feat: python -m adaptyv --json subprocess bridge (dispatch + entrypoint)"
```

---

### Task 2: Scaffold TypeScript MCP project + injectable BridgeClient

**Files:**
- Create: `mcp/package.json`
- Create: `mcp/tsconfig.json`
- Create: `mcp/.gitignore`
- Create: `mcp/src/bridge-client.ts`
- Test: `mcp/src/bridge-client.test.ts`

**Interfaces:**
- Produces (`mcp/src/bridge-client.ts`): `BridgeError extends Error` (has
  `.errorType: string`); `BridgeClient` class with
  `constructor(options?: { pythonPath?: string; cwd?: string; spawnFn?: typeof
  import("node:child_process").spawn })` and
  `call(op: string, params?: Record<string, unknown>): Promise<unknown>` (resolves
  with the bridge's `result`, rejects with `BridgeError` on `{"ok": false}` or a
  process/parse failure).

- [ ] **Step 1: Scaffold the project.** `mcp/package.json`:
```json
{
  "name": "adaptyv-mcp",
  "version": "0.1.0",
  "type": "module",
  "private": true,
  "scripts": {
    "build": "tsc",
    "start": "node dist/index.js",
    "test": "node --import tsx --test src/**/*.test.ts"
  },
  "dependencies": {
    "@modelcontextprotocol/sdk": "^1.29.0",
    "zod": "^3.25.0"
  },
  "devDependencies": {
    "typescript": "^5.6.0",
    "tsx": "^4.19.0",
    "@types/node": "^22.0.0"
  }
}
```
  `mcp/tsconfig.json`:
```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "NodeNext",
    "moduleResolution": "NodeNext",
    "outDir": "dist",
    "rootDir": "src",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "declaration": false
  },
  "include": ["src/**/*.ts"],
  "exclude": ["src/**/*.test.ts", "dist", "node_modules"]
}
```
  `mcp/.gitignore`:
```
node_modules/
dist/
```

- [ ] **Step 2: Write the failing test** — `mcp/src/bridge-client.test.ts`:
```typescript
import { test } from "node:test";
import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import { BridgeClient, BridgeError } from "./bridge-client.js";

class FakeStream extends EventEmitter {
  public written = "";
  write(chunk: string): boolean { this.written += chunk; return true; }
  end(): void {}
}

class FakeChild extends EventEmitter {
  public stdin = new FakeStream();
  public stdout = new EventEmitter();
  public stderr = new EventEmitter();
}

function fakeSpawn(response: string, opts: { closeCode?: number } = {}) {
  const child = new FakeChild();
  const calls: { command: string; args: string[] }[] = [];
  const spawnFn = ((command: string, args: string[]) => {
    calls.push({ command, args });
    queueMicrotask(() => {
      child.stdout.emit("data", Buffer.from(response));
      child.emit("close", opts.closeCode ?? 0);
    });
    return child as unknown as ReturnType<typeof import("node:child_process").spawn>;
  });
  return { spawnFn, calls, child };
}

test("call() sends op+params as JSON on stdin and returns the parsed result", async () => {
  const { spawnFn, calls, child } = fakeSpawn(JSON.stringify({ ok: true, result: { code: "EXP-1001" } }));
  const client = new BridgeClient({ spawnFn: spawnFn as any });

  const result = await client.call("get_experiment_status", { experiment_id: "abc" });

  assert.deepEqual(result, { code: "EXP-1001" });
  assert.equal(calls[0].args[0], "-m");
  assert.equal(calls[0].args[1], "adaptyv");
  assert.equal(calls[0].args[2], "--json");
  const sent = JSON.parse(child.stdin.written);
  assert.deepEqual(sent, { op: "get_experiment_status", params: { experiment_id: "abc" } });
});

test("call() rejects with BridgeError when the bridge reports ok:false", async () => {
  const { spawnFn } = fakeSpawn(JSON.stringify({ ok: false, error: { type: "NotFoundError", message: "nope" } }));
  const client = new BridgeClient({ spawnFn: spawnFn as any });

  await assert.rejects(
    () => client.call("get_experiment_status", { experiment_id: "bad" }),
    (err: unknown) => err instanceof BridgeError && err.errorType === "NotFoundError" && err.message === "nope"
  );
});

test("call() rejects with BridgeError on non-JSON bridge output", async () => {
  const { spawnFn } = fakeSpawn("not json at all");
  const client = new BridgeClient({ spawnFn: spawnFn as any });

  await assert.rejects(
    () => client.call("list_experiments", {}),
    (err: unknown) => err instanceof BridgeError && err.errorType === "BridgeProtocolError"
  );
});

test("call() defaults params to an empty object", async () => {
  const { spawnFn, child } = fakeSpawn(JSON.stringify({ ok: true, result: [] }));
  const client = new BridgeClient({ spawnFn: spawnFn as any });

  await client.call("list_experiments");

  assert.deepEqual(JSON.parse(child.stdin.written), { op: "list_experiments", params: {} });
});
```

- [ ] **Step 3: Run** `cd mcp && npm install && npm test` → FAIL
  (`Cannot find module './bridge-client.js'`).

- [ ] **Step 4: Implement** — `mcp/src/bridge-client.ts`:
```typescript
import { spawn as nodeSpawn } from "node:child_process";

export interface BridgeRequest {
  op: string;
  params?: Record<string, unknown>;
}

interface BridgeSuccess {
  ok: true;
  result: unknown;
}

interface BridgeFailure {
  ok: false;
  error: { type: string; message: string };
}

type BridgeResponse = BridgeSuccess | BridgeFailure;

export class BridgeError extends Error {
  public readonly errorType: string;
  constructor(message: string, errorType: string) {
    super(message);
    this.name = "BridgeError";
    this.errorType = errorType;
  }
}

export interface BridgeClientOptions {
  pythonPath?: string;
  cwd?: string;
  spawnFn?: typeof nodeSpawn;
}

export class BridgeClient {
  private readonly pythonPath: string;
  private readonly cwd: string | undefined;
  private readonly spawnFn: typeof nodeSpawn;

  constructor(options: BridgeClientOptions = {}) {
    this.pythonPath = options.pythonPath ?? process.env.ADAPTYV_PYTHON_PATH ?? "python3";
    this.cwd = options.cwd;
    this.spawnFn = options.spawnFn ?? nodeSpawn;
  }

  async call(op: string, params: Record<string, unknown> = {}): Promise<unknown> {
    const request: BridgeRequest = { op, params };
    const raw = await this.runProcess(JSON.stringify(request));
    let response: BridgeResponse;
    try {
      response = JSON.parse(raw) as BridgeResponse;
    } catch {
      throw new BridgeError(`bridge returned non-JSON output: ${raw}`, "BridgeProtocolError");
    }
    if (!response.ok) {
      throw new BridgeError(response.error.message, response.error.type);
    }
    return response.result;
  }

  private runProcess(input: string): Promise<string> {
    return new Promise((resolve, reject) => {
      const child = this.spawnFn(this.pythonPath, ["-m", "adaptyv", "--json"], {
        cwd: this.cwd,
        stdio: ["pipe", "pipe", "pipe"],
      });
      let stdout = "";
      let stderr = "";
      child.stdout?.on("data", (chunk: Buffer) => { stdout += chunk.toString(); });
      child.stderr?.on("data", (chunk: Buffer) => { stderr += chunk.toString(); });
      child.on("error", (err: Error) =>
        reject(new BridgeError(`failed to spawn python bridge: ${err.message}`, "BridgeSpawnError")));
      child.on("close", () => {
        if (stdout.trim().length === 0) {
          reject(new BridgeError(`bridge produced no output: ${stderr}`, "BridgeEmptyOutputError"));
          return;
        }
        resolve(stdout);
      });
      child.stdin?.write(input);
      child.stdin?.end();
    });
  }
}
```

- [ ] **Step 5: Run** `npm test` → PASS (4/4). Then type-check: `npx tsc --noEmit` → no errors.
- [ ] **Step 6: Real end-to-end smoke test (manual, not committed as a unit test — do
  this once to prove the wiring is real, then move on).** Write a throwaway script
  (do not commit it — delete it after running):
```bash
cd /Users/naloo/Programming/adaptyv-foundry/mcp
cat > /tmp/adaptyv-mcp-smoke.mjs << 'EOF'
import { BridgeClient } from "./src/bridge-client.js";
const client = new BridgeClient({ pythonPath: "../.venv/bin/python3", cwd: ".." });
const result = await client.call("list_experiments", {});
console.log(JSON.stringify(result).slice(0, 200));
EOF
node --import tsx /tmp/adaptyv-mcp-smoke.mjs
rm /tmp/adaptyv-mcp-smoke.mjs
```
  Expected: prints real mock experiment data (codes like `EXP-1001`) — confirms the TS
  process really spawns the Python bridge and gets real JSON back. Include this
  transcript in your task report.

- [ ] **Step 7: Commit**
```bash
git add mcp/package.json mcp/tsconfig.json mcp/.gitignore mcp/src/bridge-client.ts mcp/src/bridge-client.test.ts mcp/package-lock.json
git commit -m "feat: scaffold TypeScript MCP project + injectable BridgeClient"
```

---

### Task 3: ~8 task-shaped MCP tools

**Files:**
- Create: `mcp/src/tools/experiments.ts` (list_experiments, get_experiment_status,
  create_experiment_with_sequences)
- Create: `mcp/src/tools/sequences.ts` (add_sequences)
- Create: `mcp/src/tools/targets.ts` (search_targets)
- Create: `mcp/src/tools/results.ts` (get_results, estimate_cost)
- Create: `mcp/src/tools/watcher.ts` (draft_customer_update)
- Test: `mcp/src/tools/experiments.test.ts`, `mcp/src/tools/watcher.test.ts` (a
  representative sample — Task 4 broadens coverage to all 8)

**Interfaces:** Each tool module exports a factory `createXTool(bridge: BridgeClient) =>
{ name: string, config: { description: string, inputSchema: Record<string, ZodTypeAny>
}, handler: (args: any) => Promise<{ content: [{type:"text", text:string}], isError?:
boolean }> }` — the exact shape `server.registerTool(name, config, handler)` expects
(verified in Task 2's Global Constraints). Op names match Task 1's bridge dispatch
table exactly.

- [ ] **Step 1: Write the failing tests** — `mcp/src/tools/experiments.test.ts`:
```typescript
import { test } from "node:test";
import assert from "node:assert/strict";
import { createListExperimentsTool } from "./experiments.js";

function fakeBridge(result: unknown, shouldThrow?: Error) {
  return {
    call: async (_op: string, _params?: Record<string, unknown>) => {
      if (shouldThrow) throw shouldThrow;
      return result;
    },
  } as any;
}

test("list_experiments tool returns bridge result as text content", async () => {
  const tool = createListExperimentsTool(fakeBridge([{ code: "EXP-1001" }]));
  const result = await tool.handler({});
  assert.equal(tool.name, "list_experiments");
  assert.match(result.content[0].text, /EXP-1001/);
  assert.notEqual(result.isError, true);
});

test("list_experiments tool surfaces a BridgeError as isError content", async () => {
  const { BridgeError } = await import("../bridge-client.js");
  const tool = createListExperimentsTool(fakeBridge(null, new BridgeError("boom", "NotFoundError")));
  const result = await tool.handler({});
  assert.equal(result.isError, true);
  assert.match(result.content[0].text, /NotFoundError/);
  assert.match(result.content[0].text, /boom/);
});
```
  `mcp/src/tools/watcher.test.ts`:
```typescript
import { test } from "node:test";
import assert from "node:assert/strict";
import { createDraftCustomerUpdateTool } from "./watcher.js";

test("draft_customer_update tool passes experiment_id and defaults mock_llm true", async () => {
  const calls: { op: string; params?: Record<string, unknown> }[] = [];
  const bridge = { call: async (op: string, params?: Record<string, unknown>) => {
    calls.push({ op, params }); return { status: "pending_review" };
  } } as any;
  const tool = createDraftCustomerUpdateTool(bridge);

  const result = await tool.handler({ experiment_id: "exp-1" });

  assert.equal(calls[0].op, "draft_customer_update");
  assert.equal(calls[0].params?.experiment_id, "exp-1");
  assert.equal(calls[0].params?.mock_llm, true);
  assert.match(result.content[0].text, /pending_review/);
});
```

- [ ] **Step 2: Run** `npm test` → FAIL (`Cannot find module './experiments.js'` etc.).

- [ ] **Step 3: Implement a shared response helper + the 8 tools.**
  `mcp/src/tools/shared.ts`:
```typescript
import { BridgeError } from "../bridge-client.js";

export interface ToolContent {
  content: { type: "text"; text: string }[];
  isError?: boolean;
}

export async function callAndFormat(
  bridge: { call(op: string, params?: Record<string, unknown>): Promise<unknown> },
  op: string,
  params: Record<string, unknown>
): Promise<ToolContent> {
  try {
    const result = await bridge.call(op, params);
    return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
  } catch (err) {
    if (err instanceof BridgeError) {
      return { content: [{ type: "text", text: `Error (${err.errorType}): ${err.message}` }], isError: true };
    }
    return { content: [{ type: "text", text: `Unexpected error: ${(err as Error).message}` }], isError: true };
  }
}
```
  `mcp/src/tools/experiments.ts`:
```typescript
import { z } from "zod";
import type { BridgeClient } from "../bridge-client.js";
import { callAndFormat } from "./shared.js";

const EXPERIMENT_TYPES = ["affinity", "screening", "thermostability", "fluorescence",
                          "expression", "epitope_binning", "enzyme_activity"] as const;

export function createListExperimentsTool(bridge: BridgeClient) {
  return {
    name: "list_experiments",
    config: {
      description: "List lab experiments, optionally filtered by search text or a raw filter string.",
      inputSchema: {
        search: z.string().optional().describe("Free-text search over experiment name/code"),
        filter: z.string().optional().describe("Raw API filter expression"),
        sort: z.string().optional().describe("Sort expression, e.g. '-created_at'"),
        limit: z.number().int().optional(),
        offset: z.number().int().optional(),
      },
    },
    handler: async (args: Record<string, unknown>) => callAndFormat(bridge, "list_experiments", args),
  };
}

export function createGetExperimentStatusTool(bridge: BridgeClient) {
  return {
    name: "get_experiment_status",
    config: {
      description: "Get the full status, workflow state, and progress for one experiment by its UUID.",
      inputSchema: {
        experiment_id: z.string().describe("UUID of the experiment"),
      },
    },
    handler: async (args: Record<string, unknown>) => callAndFormat(bridge, "get_experiment_status", args),
  };
}

export function createCreateExperimentWithSequencesTool(bridge: BridgeClient) {
  return {
    name: "create_experiment_with_sequences",
    config: {
      description: "Create a new lab experiment and attach its protein sequences in one step.",
      inputSchema: {
        name: z.string().describe("Human-readable name for the experiment"),
        experiment_type: z.enum(EXPERIMENT_TYPES),
        sequences: z.array(z.object({
          aa_string: z.string().describe("Amino acid sequence"),
          name: z.string().optional(),
        })),
        target_id: z.string().optional().describe("UUID of a catalog target antigen, for binding assays"),
        skip_draft: z.boolean().optional(),
      },
    },
    handler: async (args: Record<string, unknown>) =>
      callAndFormat(bridge, "create_experiment_with_sequences", args),
  };
}

export { EXPERIMENT_TYPES };
```
  `mcp/src/tools/sequences.ts`:
```typescript
import { z } from "zod";
import type { BridgeClient } from "../bridge-client.js";
import { callAndFormat } from "./shared.js";

export function createAddSequencesTool(bridge: BridgeClient) {
  return {
    name: "add_sequences",
    config: {
      description: "Append additional protein sequences to an existing draft experiment.",
      inputSchema: {
        experiment_code: z.string().describe("The experiment's code, e.g. 'EXP-1001'"),
        sequences: z.array(z.object({
          aa_string: z.string(),
          name: z.string().optional(),
        })),
      },
    },
    handler: async (args: Record<string, unknown>) => callAndFormat(bridge, "add_sequences", args),
  };
}
```
  `mcp/src/tools/targets.ts`:
```typescript
import { z } from "zod";
import type { BridgeClient } from "../bridge-client.js";
import { callAndFormat } from "./shared.js";

export function createSearchTargetsTool(bridge: BridgeClient) {
  return {
    name: "search_targets",
    config: {
      description: "Search the catalog of antigen targets available for binding experiments.",
      inputSchema: {
        search: z.string().optional().describe("Free-text search, e.g. a protein name"),
        selfservice_only: z.boolean().optional(),
        detailed: z.boolean().optional(),
      },
    },
    handler: async (args: Record<string, unknown>) => callAndFormat(bridge, "search_targets", args),
  };
}
```
  `mcp/src/tools/results.ts`:
```typescript
import { z } from "zod";
import type { BridgeClient } from "../bridge-client.js";
import { callAndFormat } from "./shared.js";
import { EXPERIMENT_TYPES } from "./experiments.js";

export function createGetResultsTool(bridge: BridgeClient) {
  return {
    name: "get_results",
    config: {
      description: "Retrieve the structured results (binding affinity, kinetics, etc.) for a completed experiment.",
      inputSchema: {
        experiment_id: z.string().describe("UUID of the experiment"),
      },
    },
    handler: async (args: Record<string, unknown>) => callAndFormat(bridge, "get_results", args),
  };
}

export function createEstimateCostTool(bridge: BridgeClient) {
  return {
    name: "estimate_cost",
    config: {
      description: "Estimate the cost of an experiment configuration before creating it.",
      inputSchema: {
        experiment_type: z.enum(EXPERIMENT_TYPES),
        sequences: z.array(z.object({ aa_string: z.string(), name: z.string().optional() })).optional(),
        target_id: z.string().optional(),
      },
    },
    handler: async (args: Record<string, unknown>) => callAndFormat(bridge, "estimate_cost", args),
  };
}
```
  `mcp/src/tools/watcher.ts`:
```typescript
import { z } from "zod";
import type { BridgeClient } from "../bridge-client.js";
import { callAndFormat } from "./shared.js";

export function createDraftCustomerUpdateTool(bridge: BridgeClient) {
  return {
    name: "draft_customer_update",
    config: {
      description: "Draft a plain-English customer update email from an experiment's results, flagging any anomalies. Produces a PendingReview draft — it is never sent automatically and requires human approval.",
      inputSchema: {
        experiment_id: z.string().describe("UUID of the completed experiment"),
        mock_llm: z.boolean().optional().describe("Use a deterministic stub drafter instead of calling Claude (default true; no API key required)"),
        db: z.string().optional().describe("Path to the governance sqlite database"),
      },
    },
    handler: async (args: Record<string, unknown>) =>
      callAndFormat(bridge, "draft_customer_update", { mock_llm: true, ...args }),
  };
}
```

- [ ] **Step 4: Run** `npm test` → PASS. Type-check: `npx tsc --noEmit` → no errors.
- [ ] **Step 5: Commit**
```bash
git add mcp/src/tools/
git commit -m "feat: 8 task-shaped MCP tools (experiments, sequences, targets, results, watcher)"
```

---

### Task 4: Wire the server + broaden tool test coverage

**Files:**
- Create: `mcp/src/index.ts`
- Test: `mcp/src/tools/sequences.test.ts`, `mcp/src/tools/targets.test.ts`,
  `mcp/src/tools/results.test.ts` (the remaining tools not covered by Task 3's sample)

**Interfaces:** `mcp/src/index.ts` is the executable entrypoint: constructs one
`BridgeClient`, builds an `McpServer`, registers all 8 tools via
`server.registerTool(tool.name, tool.config, tool.handler)`, connects a
`StdioServerTransport`. No new exported interfaces — this is the composition root.

- [ ] **Step 1: Write the failing tests** — `mcp/src/tools/sequences.test.ts`:
```typescript
import { test } from "node:test";
import assert from "node:assert/strict";
import { createAddSequencesTool } from "./sequences.js";

test("add_sequences tool forwards experiment_code and sequences to the bridge", async () => {
  const calls: any[] = [];
  const bridge = { call: async (op: string, params?: any) => { calls.push({ op, params }); return { added_count: 1 }; } } as any;
  const tool = createAddSequencesTool(bridge);

  const result = await tool.handler({ experiment_code: "EXP-1001", sequences: [{ aa_string: "MKAA" }] });

  assert.equal(calls[0].op, "add_sequences");
  assert.equal(calls[0].params.experiment_code, "EXP-1001");
  assert.match(result.content[0].text, /added_count/);
});
```
  `mcp/src/tools/targets.test.ts`:
```typescript
import { test } from "node:test";
import assert from "node:assert/strict";
import { createSearchTargetsTool } from "./targets.js";

test("search_targets tool forwards search params to the bridge", async () => {
  const calls: any[] = [];
  const bridge = { call: async (op: string, params?: any) => { calls.push({ op, params }); return [{ name: "IL-6" }]; } } as any;
  const tool = createSearchTargetsTool(bridge);

  await tool.handler({ search: "IL" });

  assert.equal(calls[0].op, "search_targets");
  assert.equal(calls[0].params.search, "IL");
});
```
  `mcp/src/tools/results.test.ts`:
```typescript
import { test } from "node:test";
import assert from "node:assert/strict";
import { createGetResultsTool, createEstimateCostTool } from "./results.js";

test("get_results tool forwards experiment_id to the bridge", async () => {
  const calls: any[] = [];
  const bridge = { call: async (op: string, params?: any) => { calls.push({ op, params }); return [{ result_type: "affinity" }]; } } as any;
  const tool = createGetResultsTool(bridge);

  await tool.handler({ experiment_id: "e1" });

  assert.equal(calls[0].op, "get_results");
  assert.equal(calls[0].params.experiment_id, "e1");
});

test("estimate_cost tool forwards experiment_type and sequences to the bridge", async () => {
  const calls: any[] = [];
  const bridge = { call: async (op: string, params?: any) => { calls.push({ op, params }); return { breakdown: {} }; } } as any;
  const tool = createEstimateCostTool(bridge);

  await tool.handler({ experiment_type: "affinity", sequences: [{ aa_string: "MKAA" }] });

  assert.equal(calls[0].op, "estimate_cost");
  assert.equal(calls[0].params.experiment_type, "affinity");
});
```

- [ ] **Step 2: Run** `npm test` → PASS immediately (these test the Task 3 tools
  directly — no new source needed yet; this step just broadens coverage). Confirm all
  8 tool factories now have at least one test.

- [ ] **Step 3: Implement the composition root** — `mcp/src/index.ts`:
```typescript
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { BridgeClient } from "./bridge-client.js";
import {
  createCreateExperimentWithSequencesTool,
  createGetExperimentStatusTool,
  createListExperimentsTool,
} from "./tools/experiments.js";
import { createAddSequencesTool } from "./tools/sequences.js";
import { createSearchTargetsTool } from "./tools/targets.js";
import { createEstimateCostTool, createGetResultsTool } from "./tools/results.js";
import { createDraftCustomerUpdateTool } from "./tools/watcher.js";

async function main(): Promise<void> {
  const bridge = new BridgeClient();
  const server = new McpServer({ name: "adaptyv-foundry", version: "0.1.0" });

  const tools = [
    createListExperimentsTool(bridge),
    createGetExperimentStatusTool(bridge),
    createCreateExperimentWithSequencesTool(bridge),
    createAddSequencesTool(bridge),
    createSearchTargetsTool(bridge),
    createGetResultsTool(bridge),
    createEstimateCostTool(bridge),
    createDraftCustomerUpdateTool(bridge),
  ];
  for (const tool of tools) {
    server.registerTool(tool.name, tool.config, tool.handler);
  }

  const transport = new StdioServerTransport();
  await server.connect(transport);
}

main().catch((error) => {
  console.error("adaptyv-foundry MCP server error:", error);
  process.exit(1);
});
```

- [ ] **Step 4: Type-check + build** — `npx tsc --noEmit` → no errors;
  `npm run build` → produces `dist/index.js` with no errors.
- [ ] **Step 5: Manual smoke test (not a committed test — a real integration proof):**
```bash
cd mcp && npm run build
timeout 3 node dist/index.js < /dev/null; echo "exit: $?"
```
  Expected: the process starts, connects `StdioServerTransport` (which waits on stdin),
  and is killed cleanly by `timeout` after 3s with no stack trace printed before that —
  proving the server boots without crashing. Include this output in your report.
- [ ] **Step 6: Commit**
```bash
git add mcp/src/index.ts mcp/src/tools/sequences.test.ts mcp/src/tools/targets.test.ts mcp/src/tools/results.test.ts
git commit -m "feat: wire MCP server composition root; broaden tool test coverage to all 8 tools"
```

---

## Phase 4 Definition of Done

- `python3 -m pytest -q` fully green (Phases 1–3 + bridge tests).
- `cd mcp && npm test` fully green (all 8 tools have at least one test); `npx tsc
  --noEmit` reports no type errors; `npm run build` succeeds.
- A real (non-mocked) invocation of `BridgeClient.call()` against the actual Python
  bridge returns real mock lab data (proven once, manually, per Task 2 Step 6).
- `node mcp/dist/index.js` starts without crashing and connects a stdio transport.
- Every tool defaults to credential-free operation (`mock: true` implicitly via the
  bridge's own default; `draft_customer_update` explicitly defaults `mock_llm: true`).
- Tools are task-shaped (~8 total) with model-facing descriptions, not raw endpoint
  wrappers.

**Next (Phase 5, written just-in-time):** the eval suite (golden set + deterministic
guards as the CI gate; LLM-judge and feedback loops as labeled stretch), then Phase 6
polish (README, architecture diagram, TestPyPI as stretch).
