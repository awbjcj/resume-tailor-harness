import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { cancelRun, useLaunchRun } from "@/features/runs/use-launch-run";
import { api, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { ScrapeLimits } from "./ScrapeLimits";
import { ScrapePreview } from "./ScrapePreview";
import { defaultLimits } from "./use-scrape";

export function ScrapeImport({
  initialUrl = "",
  initialDraftId = "",
  sourceId = "",
  label = "Import public page",
}: {
  initialUrl?: string;
  initialDraftId?: string;
  sourceId?: string;
  label?: string;
}) {
  const [open, setOpen] = useState(false);
  const [url, setUrl] = useState(initialUrl);
  const [limits, setLimits] = useState(defaultLimits);
  const [runId, setRunId] = useState("");
  const cache = useQueryClient();
  const { launch } = useLaunchRun();
  const run = useQuery({
    queryKey: ["scrape-run", runId],
    enabled: !!runId && open,
    queryFn: () =>
      unwrap(
        api.GET("/api/runs/{run_id}", { params: { path: { run_id: runId } } }),
      ),
    refetchInterval: (query) =>
      ["done", "error", "cancelled"].includes(query.state.data?.state ?? "")
        ? false
        : 1500,
  });
  const savedDraft = useQuery({
    queryKey: ["scrape-edit", sourceId],
    enabled: !!sourceId && open,
    staleTime: Infinity,
    queryFn: () =>
      unwrap(
        api.POST("/api/scrape/sources/{source_id}/edit", {
          params: { path: { source_id: sourceId } },
        }),
      ),
  });
  const result = run.data?.result;
  const draftId =
    result &&
    typeof result === "object" &&
    "draftId" in result &&
    typeof result.draftId === "string"
      ? result.draftId
      : initialDraftId || savedDraft.data?.id || "";
  const working =
    !!runId &&
    !["done", "error", "cancelled"].includes(run.data?.state ?? "pending");
  useEffect(() => {
    if (run.data?.state === "done")
      void cache.invalidateQueries({ queryKey: ["scrape-draft"] });
  }, [run.data?.state, runId, cache]);
  async function start(call: () => Promise<components["schemas"]["RunOut"]>) {
    await launch(
      "scrapeAnalyze",
      async () => {
        const value = await call();
        setRunId(value.runId);
        return value;
      },
      ["scrape-sources", "sources", "triage"],
    );
  }
  return (
    <Dialog
      open={open}
      onOpenChange={(value) => {
        setOpen(value);
        if (value && initialUrl) setUrl(initialUrl);
      }}
    >
      <DialogTrigger render={<Button variant="outline" size="sm" />}>
        {label}
      </DialogTrigger>
      <DialogContent className="max-h-[90svh] overflow-y-auto sm:max-w-4xl">
        <DialogHeader>
          <DialogTitle>Review public job page</DialogTitle>
          <DialogDescription>
            Inspect public postings, correct extracted fields, and save reusable
            rules.
          </DialogDescription>
        </DialogHeader>
        {savedDraft.error && <p role="alert">{savedDraft.error.message}</p>}
        {!draftId && !sourceId && (
          <>
            <label className="space-y-1 text-sm">
              Public job or board URL
              <Input
                value={url}
                onChange={(event) => setUrl(event.target.value)}
                placeholder="https://example.com/careers"
              />
            </label>
            <ScrapeLimits value={limits} onChange={setLimits} />
            <Button
              disabled={!url.trim() || working}
              onClick={() =>
                void start(() =>
                  unwrap(
                    api.POST("/api/scrape/drafts", { body: { url, limits } }),
                  ),
                )
              }
            >
              Analyze page
            </Button>
          </>
        )}
        {working && (
          <div role="status" className="space-y-2">
            <p>{run.data?.label || "Inspecting public page…"}</p>
            <p className="text-sm text-muted-foreground">
              Requests are paced to respect the website. This may take several
              minutes.
            </p>
            <Button variant="secondary" onClick={() => void cancelRun(runId)}>
              Cancel
            </Button>
          </div>
        )}
        {(run.error || run.data?.error) && (
          <p role="alert" className="text-destructive">
            {run.error?.message || run.data?.error}
          </p>
        )}
        {draftId && !working && (
          <ScrapePreview
            draftId={draftId}
            onApproved={() => {
              void cache.invalidateQueries({ queryKey: ["scrape-sources"] });
              void cache.invalidateQueries({ queryKey: ["triage"] });
              void cache.removeQueries({ queryKey: ["scrape-edit", sourceId] });
              setOpen(false);
            }}
            onValidate={(id, revision) =>
              void start(() =>
                unwrap(
                  api.POST("/api/scrape/drafts/{draft_id}/validate", {
                    params: { path: { draft_id: id } },
                    body: { expectedRevision: revision },
                  }),
                ),
              )
            }
          />
        )}
      </DialogContent>
    </Dialog>
  );
}
