import { BridgeError } from "../bridge-client.js";

export interface ToolContent {
  content: { type: "text"; text: string }[];
  isError?: boolean;
}

export async function callAndFormat(
  bridge: { call(op: string, params?: Record<string, unknown>): Promise<unknown> },
  op: string,
  params: Record<string, unknown>
): Promise<ToolContent> {
  try {
    const result = await bridge.call(op, params);
    return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
  } catch (err) {
    if (err instanceof BridgeError) {
      return { content: [{ type: "text", text: `Error (${err.errorType}): ${err.message}` }], isError: true };
    }
    return { content: [{ type: "text", text: `Unexpected error: ${(err as Error).message}` }], isError: true };
  }
}
