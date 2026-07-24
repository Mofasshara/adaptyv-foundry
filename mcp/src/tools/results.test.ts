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
