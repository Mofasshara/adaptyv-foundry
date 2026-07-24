import { test } from "node:test";
import assert from "node:assert/strict";
import {
  createCreateExperimentWithSequencesTool,
  createGetExperimentStatusTool,
  createListExperimentsTool,
} from "./experiments.js";

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

test("get_experiment_status tool forwards experiment_id and returns the bridge result", async () => {
  const calls: { op: string; params?: Record<string, unknown> }[] = [];
  const bridge = {
    call: async (op: string, params?: Record<string, unknown>) => {
      calls.push({ op, params });
      return { code: "EXP-1001", status: "done" };
    },
  } as any;
  const tool = createGetExperimentStatusTool(bridge);

  const result = await tool.handler({ experiment_id: "11111111-1111-1111-1111-111111111111" });

  assert.equal(tool.name, "get_experiment_status");
  assert.equal(calls[0].op, "get_experiment_status");
  assert.equal(calls[0].params?.experiment_id, "11111111-1111-1111-1111-111111111111");
  assert.match(result.content[0].text, /EXP-1001/);
  assert.notEqual(result.isError, true);
});

test("create_experiment_with_sequences tool forwards name, type, and sequences to the bridge", async () => {
  const calls: { op: string; params?: Record<string, unknown> }[] = [];
  const bridge = {
    call: async (op: string, params?: Record<string, unknown>) => {
      calls.push({ op, params });
      return { experiment_id: "99999999-9999-9999-9999-999999999999" };
    },
  } as any;
  const tool = createCreateExperimentWithSequencesTool(bridge);

  const result = await tool.handler({
    name: "MCP test run",
    experiment_type: "affinity",
    sequences: [{ aa_string: "MKAA", name: "binder-x" }],
  });

  assert.equal(tool.name, "create_experiment_with_sequences");
  assert.equal(calls[0].op, "create_experiment_with_sequences");
  assert.equal(calls[0].params?.name, "MCP test run");
  assert.equal(calls[0].params?.experiment_type, "affinity");
  assert.deepEqual(calls[0].params?.sequences, [{ aa_string: "MKAA", name: "binder-x" }]);
  assert.match(result.content[0].text, /experiment_id/);
});
