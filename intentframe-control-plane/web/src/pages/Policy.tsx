import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef } from "react";
import { Alert, Button, Card, PageHeader } from "../components/ui";
import { api } from "../api/client";

export default function PolicyPage() {
  const queryClient = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);

  const { data, isLoading, error } = useQuery({
    queryKey: ["policy"],
    queryFn: api.policy,
  });

  const reloadMutation = useMutation({
    mutationFn: api.reloadPolicy,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["policy"] }),
  });

  const resetMutation = useMutation({
    mutationFn: api.resetPolicy,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["policy"] }),
  });

  const uploadMutation = useMutation({
    mutationFn: (file: File) => api.applyPolicyFile(file),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["policy"] }),
  });

  return (
    <>
      <PageHeader
        title="Policy"
        description="Runtime ALLOW/BLOCK rules loaded into IntentFrame policy registry."
      />

      {error ? <Alert tone="warn">{(error as Error).message}</Alert> : null}

      <Card className="mb-4">
        {isLoading || !data ? (
          <div>Loading policy…</div>
        ) : (
          <div className="space-y-2 text-sm text-slate-300">
            <div>
              Runtime: <code className="text-cyan-200">{String(data.meta.runtime_path)}</code>
            </div>
            <div>Registry: {String(data.meta.registry_message)}</div>
          </div>
        )}
      </Card>

      <Card>
        <pre className="max-h-[480px] overflow-auto rounded-lg bg-slate-950 p-4 text-xs leading-relaxed text-slate-300">
          {data?.yaml || (isLoading ? "Loading…" : "No policy file")}
        </pre>
      </Card>

      <div className="mt-4 flex flex-wrap gap-3">
        <input
          ref={fileRef}
          type="file"
          accept=".yaml,.yml"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) uploadMutation.mutate(file);
            e.target.value = "";
          }}
        />
        <Button variant="secondary" onClick={() => fileRef.current?.click()} disabled={uploadMutation.isPending}>
          {uploadMutation.isPending ? "Uploading…" : "Upload & apply policy"}
        </Button>
        <Button variant="secondary" onClick={() => reloadMutation.mutate()} disabled={reloadMutation.isPending}>
          {reloadMutation.isPending ? "Reloading…" : "Reload from disk"}
        </Button>
        <Button
          variant="danger"
          onClick={() => {
            if (window.confirm("Reset policy to shipped default?")) resetMutation.mutate();
          }}
          disabled={resetMutation.isPending}
        >
          {resetMutation.isPending ? "Resetting…" : "Reset to default"}
        </Button>
      </div>

      {(reloadMutation.error || resetMutation.error || uploadMutation.error) && (
        <Alert tone="warn">
          {((reloadMutation.error ?? resetMutation.error ?? uploadMutation.error) as Error).message}
        </Alert>
      )}
    </>
  );
}
