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
        method: z.enum(["bli", "spr"]).optional()
          .describe("Measurement method — required by the API for affinity/screening experiments"),
        n_replicates: z.number().int().optional().describe("Number of technical replicates"),
        sequences: z.array(z.object({ aa_string: z.string(), name: z.string().optional() })).optional(),
        target_id: z.string().optional(),
      },
    },
    handler: async (args: Record<string, unknown>) => callAndFormat(bridge, "estimate_cost", args),
  };
}
