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
