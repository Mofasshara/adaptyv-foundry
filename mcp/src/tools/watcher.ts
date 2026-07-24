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
