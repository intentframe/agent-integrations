export interface BridgeClientConfig {
  socketPath: string;
  secret: string;
  timeoutMs?: number;
}

export interface HandshakeCapabilities {
  agent_type?: string;
  description?: string;
  action_types?: string[];
  capabilities?: string[];
  resource_needs?: string[];
  version?: string;
  author?: string;
}

export interface RuntimeContext {
  user_id?: string;
  agent_id?: string;
  session_id?: string;
  guardrails?: string[];
  [key: string]: unknown;
}

export interface ValidateRequest {
  action: string;
  reason: string;
  target?: string;
  command?: string;
  display_subject?: string;
  [key: string]: unknown;
}

export interface ValidateResponse {
  allowed: boolean;
  success: boolean;
  validated_only?: boolean;
  decision?: string | null;
  error?: string | null;
  data?: Record<string, unknown>;
  agent_id?: string;
  user_id?: string;
  [key: string]: unknown;
}
