import path from "node:path";
import { fileURLToPath } from "node:url";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { BridgeClient } from "./bridge-client.js";
import {
  createCreateExperimentWithSequencesTool,
  createGetExperimentStatusTool,
  createListExperimentsTool,
} from "./tools/experiments.js";
import { createAddSequencesTool } from "./tools/sequences.js";
import { createSearchTargetsTool } from "./tools/targets.js";
import { createEstimateCostTool, createGetResultsTool } from "./tools/results.js";
import { createDraftCustomerUpdateTool } from "./tools/watcher.js";

// This file lives at <repo-root>/mcp/src/index.ts, so the repo root is two
// directories up from here. We must resolve the venv's python3 to an ABSOLUTE
// path computed from this file's own location (not process.cwd()) because an
// MCP client (e.g. Claude Desktop) spawns this server from an arbitrary working
// directory it controls. node:child_process.spawn() resolves a relative command
// string against the CHILD's cwd (POSIX exec semantics), so a bare relative
// string like "../.venv/bin/python3" would break as soon as this process isn't
// launched with cwd === mcp/.
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DEFAULT_PYTHON_PATH = path.resolve(__dirname, "../../.venv/bin/python3");

async function main(): Promise<void> {
  const pythonPath = process.env.ADAPTYV_PYTHON_PATH ?? DEFAULT_PYTHON_PATH;
  const bridge = new BridgeClient({ pythonPath });
  const server = new McpServer({ name: "adaptyv-foundry", version: "0.1.0" });

  // Every tool factory returns a handler typed as
  // `(args: Record<string, unknown>) => Promise<ToolContent>` (see tools/shared.ts).
  // `ToolContent` is a plain interface without an index signature, while the SDK's
  // `ToolCallback` return type (`CallToolResult`) is a zod-inferred type that carries
  // one (`[x: string]: unknown`) for protocol extensibility, and its argument type is
  // a per-tool conditional type keyed off each tool's own zod input schema. The two
  // shapes are structurally compatible at runtime (every tool here takes a single
  // parsed-args object and returns `{ content, isError? }`), but distributing a
  // shared helper across 8 differently-shaped schemas defeats structural narrowing,
  // so we bridge with a targeted `any` here. This doesn't affect the `config`/
  // `inputSchema` argument passed alongside it, which still type-checks per tool.
  const asToolCallback = (handler: (args: Record<string, unknown>) => Promise<unknown>): any => handler;

  const listExperiments = createListExperimentsTool(bridge);
  server.registerTool(listExperiments.name, listExperiments.config, asToolCallback(listExperiments.handler));

  const getExperimentStatus = createGetExperimentStatusTool(bridge);
  server.registerTool(
    getExperimentStatus.name,
    getExperimentStatus.config,
    asToolCallback(getExperimentStatus.handler)
  );

  const createExperimentWithSequences = createCreateExperimentWithSequencesTool(bridge);
  server.registerTool(
    createExperimentWithSequences.name,
    createExperimentWithSequences.config,
    asToolCallback(createExperimentWithSequences.handler)
  );

  const addSequences = createAddSequencesTool(bridge);
  server.registerTool(addSequences.name, addSequences.config, asToolCallback(addSequences.handler));

  const searchTargets = createSearchTargetsTool(bridge);
  server.registerTool(searchTargets.name, searchTargets.config, asToolCallback(searchTargets.handler));

  const getResults = createGetResultsTool(bridge);
  server.registerTool(getResults.name, getResults.config, asToolCallback(getResults.handler));

  const estimateCost = createEstimateCostTool(bridge);
  server.registerTool(estimateCost.name, estimateCost.config, asToolCallback(estimateCost.handler));

  const draftCustomerUpdate = createDraftCustomerUpdateTool(bridge);
  server.registerTool(
    draftCustomerUpdate.name,
    draftCustomerUpdate.config,
    asToolCallback(draftCustomerUpdate.handler)
  );

  const transport = new StdioServerTransport();
  await server.connect(transport);
}

main().catch((error) => {
  console.error("adaptyv-foundry MCP server error:", error);
  process.exit(1);
});
