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
