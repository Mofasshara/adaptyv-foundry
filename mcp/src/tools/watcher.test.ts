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
