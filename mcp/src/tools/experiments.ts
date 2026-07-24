import { z } from "zod";
import type { BridgeClient } from "../bridge-client.js";
import { callAndFormat } from "./shared.js";

const EXPERIMENT_TYPES = ["affinity", "screening", "thermostability", "fluorescence",
                          "expression", "epitope_binning", "enzyme_activity"] as const;

export function createListExperimentsTool(bridge: BridgeClient) {
  return {
    name: "list_experiments",
    config: {
      description: "List lab experiments, optionally filtered by search text or a raw filter string.",
      inputSchema: {
        search: z.string().optional().describe("Free-text search over experiment name/code"),
        filter: z.string().optional().describe("Raw API filter expression"),
        sort: z.string().optional().describe("Sort expression, e.g. '-created_at'"),
        limit: z.number().int().optional(),
        offset: z.number().int().optional(),
      },
    },
    handler: async (args: Record<string, unknown>) => callAndFormat(bridge, "list_experiments", args),
  };
}

export function createGetExperimentStatusTool(bridge: BridgeClient) {
  return {
    name: "get_experiment_status",
    config: {
      description: "Get the full status, workflow state, and progress for one experiment by its UUID.",
      inputSchema: {
        experiment_id: z.string().describe("UUID of the experiment"),
      },
    },
    handler: async (args: Record<string, unknown>) => callAndFormat(bridge, "get_experiment_status", args),
  };
}

export function createCreateExperimentWithSequencesTool(bridge: BridgeClient) {
  return {
    name: "create_experiment_with_sequences",
    config: {
      description: "Create a new lab experiment and attach its protein sequences in one step.",
      inputSchema: {
        name: z.string().describe("Human-readable name for the experiment"),
        experiment_type: z.enum(EXPERIMENT_TYPES),
        sequences: z.array(z.object({
          aa_string: z.string().describe("Amino acid sequence"),
          name: z.string().optional(),
        })),
        target_id: z.string().optional().describe("UUID of a catalog target antigen, for binding assays"),
        skip_draft: z.boolean().optional(),
      },
    },
    handler: async (args: Record<string, unknown>) =>
      callAndFormat(bridge, "create_experiment_with_sequences", args),
  };
}

export { EXPERIMENT_TYPES };
