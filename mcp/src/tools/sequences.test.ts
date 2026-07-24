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
