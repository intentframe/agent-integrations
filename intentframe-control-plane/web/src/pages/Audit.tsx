import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Alert, Button, Card, PageHeader } from "../components/ui";
import { api } from "../api/client";

export default function AuditPage() {
  const [autoRefresh, setAutoRefresh] = useState(true);
  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ["audit"],
    queryFn: () => api.auditLog(300),
    refetchInterval: autoRefresh ? 5000 : false,
  });

  return (
    <>
      <PageHeader
        title="Audit"
        description="Tail of IntentFrame server log (ALLOW/BLOCK decisions)."
      />

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Button variant="secondary" onClick={() => refetch()} disabled={isFetching}>
          {isFetching ? "Refreshing…" : "Refresh"}
        </Button>
        <label className="inline-flex items-center gap-2 text-sm text-slate-300">
          <input
            type="checkbox"
            checked={autoRefresh}
            onChange={(e) => setAutoRefresh(e.target.checked)}
            className="h-4 w-4 rounded border-slate-600 bg-slate-800"
          />
          Auto-refresh every 5s
        </label>
        {data?.path ? <span className="text-xs text-slate-500">{data.path}</span> : null}
      </div>

      {error ? <Alert tone="warn">{(error as Error).message}</Alert> : null}

      <Card>
        <pre className="max-h-[640px] overflow-auto whitespace-pre-wrap break-all font-mono text-xs leading-relaxed text-slate-300">
          {isLoading
            ? "Loading log…"
            : data?.lines.length
              ? data.lines.join("\n")
              : "Log file empty or not found."}
        </pre>
      </Card>
    </>
  );
}
