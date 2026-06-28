import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Badge, Button, Card, PageHeader } from "../components/ui";
import { api } from "../api/client";

export default function OverviewPage() {
  const queryClient = useQueryClient();
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["status"],
    queryFn: api.status,
    refetchInterval: 5000,
  });

  const upMutation = useMutation({
    mutationFn: api.stackUp,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["status"] }),
  });

  const stopMutation = useMutation({
    mutationFn: api.stackStop,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["status"] }),
  });

  const adapter = data?.adapters[0];
  const stackUp =
    data?.bridge_present && adapter?.running && data.gateway_running;

  return (
    <>
      <PageHeader
        title="Overview"
        description="IntentFrame enforcement stack status. Hermes chat runs separately on port 9119."
      />

      {!data?.openai_api_key_set ? (
        <Alert tone="warn">
          OPENAI_API_KEY is not set in the environment. Export it in your shell, then start the
          enforcement stack.
        </Alert>
      ) : null}

      {error ? (
        <Alert tone="warn">{(error as Error).message}</Alert>
      ) : isLoading || !data ? (
        <Card>Loading status…</Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          <Card>
            <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-slate-400">
              Enforcement
            </h2>
            <div className="space-y-2 text-sm">
              <div className="flex items-center justify-between gap-2">
                <span>Backend bridge</span>
                <Badge ok={data.bridge_present} label={data.bridge_present ? "up" : "down"} />
              </div>
              <div className="flex items-center justify-between gap-2">
                <span>Adapter ({adapter?.agent_id ?? "hermes"})</span>
                <Badge ok={!!adapter?.running} label={adapter?.running ? "running" : "stopped"} />
              </div>
              <div className="flex items-center justify-between gap-2">
                <span>Hermes gateway</span>
                <Badge ok={data.gateway_running} label={data.gateway_running ? "running" : "stopped"} />
              </div>
            </div>
          </Card>

          <Card>
            <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-slate-400">
              Control plane
            </h2>
            <div className="space-y-2 text-sm">
              <div className="flex items-center justify-between gap-2">
                <span>UI server</span>
                <Badge
                  ok={data.control_plane.healthy}
                  label={data.control_plane.healthy ? "healthy" : "unhealthy"}
                />
              </div>
              <div className="text-slate-400">{data.control_plane.url}</div>
            </div>
          </Card>
        </div>
      )}

      <div className="mt-6 flex flex-wrap gap-3">
        <Button
          onClick={() => upMutation.mutate()}
          disabled={upMutation.isPending || !!stackUp}
        >
          {upMutation.isPending ? "Starting…" : "Start enforcement stack"}
        </Button>
        <Button
          variant="danger"
          onClick={() => {
            if (window.confirm("Stop the enforcement stack? Control plane will keep running.")) {
              stopMutation.mutate();
            }
          }}
          disabled={stopMutation.isPending}
        >
          {stopMutation.isPending ? "Stopping…" : "Stop enforcement stack"}
        </Button>
        <Button variant="secondary" onClick={() => refetch()}>
          Refresh
        </Button>
      </div>

      {(upMutation.error || stopMutation.error) && (
        <Alert tone="warn" >
          {((upMutation.error ?? stopMutation.error) as Error).message}
        </Alert>
      )}
    </>
  );
}
