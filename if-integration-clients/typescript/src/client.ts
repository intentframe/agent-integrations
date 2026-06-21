import { homedir } from "node:os";
import { join } from "node:path";
import { Agent, fetch, type RequestInit } from "undici";

import { BridgeHttpError } from "./errors.js";
import type {
  BridgeClientConfig,
  HandshakeCapabilities,
  RuntimeContext,
  ValidateRequest,
  ValidateResponse,
} from "./types.js";

function expandHome(path: string): string {
  return path.startsWith("~/") ? join(homedir(), path.slice(2)) : path;
}

export class BridgeClient {
  readonly config: BridgeClientConfig;
  runtimeContext: RuntimeContext | null = null;

  constructor(config: BridgeClientConfig) {
    this.config = config;
  }

  static fromEnv(
    env: NodeJS.ProcessEnv = process.env,
    defaults: { socketPath?: string } = {},
  ): BridgeClient {
    const secret = env.IF_AGENT_BRIDGE_SECRET;
    if (!secret) {
      throw new Error("IF_AGENT_BRIDGE_SECRET is required");
    }
    const socketPath =
      env.IF_SECURITY_BRIDGE_SOCKET ??
      defaults.socketPath ??
      "~/.intentframe/backend/bridge.sock";
    return new BridgeClient({ socketPath, secret });
  }

  private dispatcher(): Agent {
    return new Agent({ connect: { socketPath: expandHome(this.config.socketPath) } });
  }

  private headers(): Record<string, string> {
    return {
      Authorization: `Bearer ${this.config.secret}`,
      "Content-Type": "application/json",
    };
  }

  private async post(path: string, body: unknown): Promise<{ status: number; json: unknown }> {
    const init: RequestInit = {
      method: "POST",
      dispatcher: this.dispatcher(),
      headers: this.headers(),
      body: JSON.stringify(body),
    };
    const res = await fetch(`http://bridge${path}`, init);
    return { status: res.status, json: await res.json() };
  }

  async handshake(capabilities: HandshakeCapabilities = {}): Promise<RuntimeContext> {
    const { status, json } = await this.post("/handshake", capabilities);
    if (status >= 400) {
      throw new BridgeHttpError(status, json);
    }
    this.runtimeContext = json as RuntimeContext;
    return this.runtimeContext;
  }

  async validate(request: ValidateRequest): Promise<ValidateResponse> {
    const { status, json } = await this.post("/validate", request);
    if (status >= 400) {
      throw new BridgeHttpError(status, json);
    }
    return json as ValidateResponse;
  }

  async validateRunCommand(opts: {
    command: string;
    reason: string;
    target?: string;
    [key: string]: unknown;
  }): Promise<ValidateResponse> {
    const { command, reason, target, ...extra } = opts;
    return this.validate({
      action: "RUN_COMMAND",
      command,
      reason,
      target: target ?? command.slice(0, 200),
      ...extra,
    });
  }

  async validateRaw(request: ValidateRequest): Promise<{ status: number; body: ValidateResponse }> {
    const { status, json } = await this.post("/validate", request);
    return { status, body: json as ValidateResponse };
  }

  async validateExpectStatus(
    request: ValidateRequest,
    statusCode: number,
  ): Promise<ValidateResponse> {
    const { status, body } = await this.validateRaw(request);
    if (status !== statusCode) {
      throw new BridgeHttpError(status, body, statusCode);
    }
    return body;
  }
}
