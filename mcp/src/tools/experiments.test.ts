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
