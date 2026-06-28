import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Alert, Button, Card, PageHeader } from "../components/ui";
import { api } from "../api/client";

export default function GovernancePage() {
  const queryClient = useQueryClient();
  const { data, isLoading, error } = useQuery({
    queryKey: ["governance"],
    queryFn: api.governance,
  });

  const [pending, setPending] = useState<Record<string, boolean>>({});

  const dirty = useMemo(() => {
    if (!data) return false;
    return data.tools.some((tool) => pending[tool.name] !== undefined && pending[tool.name] !== tool.enabled);
  }, [data, pending]);

  const toggleMutation = useMutation({
    mutationFn: async ({ name, enabled }: { name: string; enabled: boolean }) => {
      if (enabled) await api.enableTool(name);
      else await api.disableTool(name);
    },
  });

  const applyMutation = useMutation({
    mutationFn: async () => {
      if (!data) return;
      for (const tool of data.tools) {
        const desired = pending[tool.name];
        if (desired === undefined || desired === tool.enabled) continue;
        await toggleMutation.mutateAsync({ name: tool.name, enabled: desired });
      }
      await api.applyGovernance();
    },
    onSuccess: () => {
      setPending({});
      queryClient.invalidateQueries({ queryKey: ["governance"] });
      queryClient.invalidateQueries({ queryKey: ["status"] });
    },
  });

  return (
    <>
      <PageHeader
        title="Governance"
        description="Choose which Hermes tools IntentFrame validates before execution."
      />
      <Alert tone="info">
        Changes require a gateway restart. Use Apply &amp; restart gateway after editing toggles.
      </Alert>

      {error ? <Alert tone="warn">{(error as Error).message}</Alert> : null}

      <Card>
        {isLoading || !data ? (
          <div>Loading governed tools…</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="text-slate-400">
                <tr>
                  <th className="pb-3 pr-4 font-medium">Tool</th>
                  <th className="pb-3 pr-4 font-medium">Runtime</th>
                  <th className="pb-3 font-medium">Governed</th>
                </tr>
              </thead>
              <tbody>
                {data.tools.map((tool) => {
                  const enabled = pending[tool.name] ?? tool.enabled;
                  return (
                    <tr key={tool.name} className="border-t border-slate-800">
                      <td className="py-3 pr-4 font-mono text-cyan-200">{tool.name}</td>
                      <td className="py-3 pr-4 text-slate-400">
                        {tool.enabled ? "enabled" : "disabled"}
                      </td>
                      <td className="py-3">
                        <label className="inline-flex cursor-pointer items-center gap-2">
                          <input
                            type="checkbox"
                            checked={enabled}
                            onChange={(e) =>
                              setPending((prev) => ({ ...prev, [tool.name]: e.target.checked }))
                            }
                            className="h-4 w-4 rounded border-slate-600 bg-slate-800"
                          />
                          <span>{enabled ? "governed" : "ungoverned"}</span>
                        </label>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <div className="mt-4 flex gap-3">
        <Button
          disabled={!dirty || applyMutation.isPending}
          onClick={() => applyMutation.mutate()}
        >
          {applyMutation.isPending ? "Applying…" : "Apply & restart gateway"}
        </Button>
        <Button variant="secondary" onClick={() => setPending({})} disabled={!dirty}>
          Reset toggles
        </Button>
      </div>

      {applyMutation.error ? (
        <Alert tone="warn">{(applyMutation.error as Error).message}</Alert>
      ) : null}
    </>
  );
}
