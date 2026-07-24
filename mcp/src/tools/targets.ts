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
