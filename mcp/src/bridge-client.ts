import { spawn as nodeSpawn } from "node:child_process";

export interface BridgeRequest {
  op: string;
  params?: Record<string, unknown>;
}

interface BridgeSuccess {
  ok: true;
  result: unknown;
}

interface BridgeFailure {
  ok: false;
  error: { type: string; message: string };
}

type BridgeResponse = BridgeSuccess | BridgeFailure;

export class BridgeError extends Error {
  public readonly errorType: string;
  constructor(message: string, errorType: string) {
    super(message);
    this.name = "BridgeError";
    this.errorType = errorType;
  }
}

export interface BridgeClientOptions {
  pythonPath?: string;
  cwd?: string;
  spawnFn?: typeof nodeSpawn;
}

export class BridgeClient {
  private readonly pythonPath: string;
  private readonly cwd: string | undefined;
  private readonly spawnFn: typeof nodeSpawn;

  constructor(options: BridgeClientOptions = {}) {
    this.pythonPath = options.pythonPath ?? process.env.ADAPTYV_PYTHON_PATH ?? "python3";
    this.cwd = options.cwd;
    this.spawnFn = options.spawnFn ?? nodeSpawn;
  }

  async call(op: string, params: Record<string, unknown> = {}): Promise<unknown> {
    const request: BridgeRequest = { op, params };
    const raw = await this.runProcess(JSON.stringify(request));
    let response: BridgeResponse;
    try {
      response = JSON.parse(raw) as BridgeResponse;
    } catch {
      throw new BridgeError(`bridge returned non-JSON output: ${raw}`, "BridgeProtocolError");
    }
    if (!response.ok) {
      throw new BridgeError(response.error.message, response.error.type);
    }
    return response.result;
  }

  private runProcess(input: string): Promise<string> {
    return new Promise((resolve, reject) => {
      const child = this.spawnFn(this.pythonPath, ["-m", "adaptyv", "--json"], {
        cwd: this.cwd,
        stdio: ["pipe", "pipe", "pipe"],
      });
      let stdout = "";
      let stderr = "";
      child.stdout?.on("data", (chunk: Buffer) => { stdout += chunk.toString(); });
      child.stderr?.on("data", (chunk: Buffer) => { stderr += chunk.toString(); });
      child.on("error", (err: Error) =>
        reject(new BridgeError(`failed to spawn python bridge: ${err.message}`, "BridgeSpawnError")));
      child.on("close", () => {
        if (stdout.trim().length === 0) {
          reject(new BridgeError(`bridge produced no output: ${stderr}`, "BridgeEmptyOutputError"));
          return;
        }
        resolve(stdout);
      });
      child.stdin?.write(input);
      child.stdin?.end();
    });
  }
}
