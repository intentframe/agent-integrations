export type ApiResponse<T> = {
  ok: boolean;
  data?: T;
  error?: string;
};

export type StatusData = {
  bridge_socket: string;
  bridge_present: boolean;
  gateway_running: boolean;
  gateway_pid: number | null;
  adapters: Array<{
    agent_id: string;
    running: boolean;
    pid: number | null;
    socket: string;
  }>;
  control_plane: {
    running: boolean;
    healthy: boolean;
    pid: number | null;
    url: string;
  };
  openai_api_key_set: boolean;
};

export type GovernanceData = {
  agent: string;
  tools: Array<{ name: string; enabled: boolean }>;
  runtime_governed: string[];
};

export type PolicyData = {
  meta: Record<string, unknown>;
  yaml: string;
};

export type PublicConfig = {
  hermes_chat_url: string;
};

async function request<T>(
  path: string,
  init?: RequestInit & { confirm?: boolean },
): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.confirm) {
    headers.set("X-Confirm", "true");
  }
  const res = await fetch(path, { ...init, headers });
  let body: ApiResponse<T>;
  try {
    body = (await res.json()) as ApiResponse<T>;
  } catch {
    throw new Error(`Request failed (${res.status})`);
  }
  if (!body.ok) {
    throw new Error(body.error ?? `Request failed (${res.status})`);
  }
  return body.data as T;
}

export const api = {
  config: () => request<PublicConfig>("/api/config"),
  status: () => request<StatusData>("/api/status"),
  governance: () => request<GovernanceData>("/api/governance"),
  enableTool: (tool: string) =>
    request<{ message: string }>(`/api/governance/${tool}/enable`, { method: "POST" }),
  disableTool: (tool: string) =>
    request<{ message: string }>(`/api/governance/${tool}/disable`, { method: "POST" }),
  applyGovernance: () =>
    request<{ stop: string; start: string }>("/api/governance/apply", { method: "POST" }),
  policy: () => request<PolicyData>("/api/policy"),
  reloadPolicy: () =>
    request<{ message: string }>("/api/policy/reload", { method: "POST" }),
  resetPolicy: () =>
    request<{ message: string }>("/api/policy/reset", { method: "POST", confirm: true }),
  stackUp: () => request<{ message: string }>("/api/stack/up", { method: "POST" }),
  stackStop: () =>
    request<{ message: string }>("/api/stack/stop", { method: "POST", confirm: true }),
  auditLog: (tail = 200) =>
    request<{ lines: string[]; path: string }>(`/api/audit/log?tail=${tail}`),
  applyPolicyFile: async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch("/api/policy/apply", { method: "POST", body: form });
    const body = (await res.json()) as ApiResponse<{ message: string }>;
    if (!body.ok) throw new Error(body.error ?? "Upload failed");
    return body.data!;
  },
};
