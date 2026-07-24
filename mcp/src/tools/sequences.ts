import { z } from "zod";
import type { BridgeClient } from "../bridge-client.js";
import { callAndFormat } from "./shared.js";

export function createAddSequencesTool(bridge: BridgeClient) {
  return {
    name: "add_sequences",
    config: {
      description: "Append additional protein sequences to an existing draft experiment.",
      inputSchema: {
        experiment_code: z.string().describe("The experiment's code, e.g. 'EXP-1001'"),
        sequences: z.array(z.object({
          aa_string: z.string(),
          name: z.string().optional(),
        })),
      },
    },
    handler: async (args: Record<string, unknown>) => callAndFormat(bridge, "add_sequences", args),
  };
}
