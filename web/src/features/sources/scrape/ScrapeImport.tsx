import { useEffect, useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Globe2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PublicUrlField, isPublicHttpUrl } from "@/components/PublicUrlField";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
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
  label = "Add job board URL",
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
  const [urlTouched, setUrlTouched] = useState(false);
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
  const urlIsValid = isPublicHttpUrl(url);
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setUrlTouched(true);
    if (!urlIsValid || working) return;
    void start(() =>
      unwrap(
        api.POST("/api/scrape/drafts", {
          body: { url: url.trim(), limits },
        }),
      ),
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
      <DialogContent
        className={`max-h-[90svh] overflow-y-auto ${draftId || sourceId ? "sm:max-w-4xl" : "sm:max-w-lg"}`}
      >
        <DialogHeader>
          <DialogTitle>Review public job page</DialogTitle>
          <DialogDescription>
            Add a public careers page, review a sample of its postings, and save
            reusable import rules.
          </DialogDescription>
        </DialogHeader>
        {savedDraft.error && <p role="alert">{savedDraft.error.message}</p>}
        {!draftId && !sourceId && (
          <form className="space-y-4" noValidate onSubmit={submit}>
            <div className="space-y-4 rounded-xl border bg-muted/25 p-4">
              <PublicUrlField
                id="public-board-url"
                label="Job board URL"
                value={url}
                placeholder="https://example.com/careers"
                invalid={urlTouched && !urlIsValid}
                onBlur={() => setUrlTouched(true)}
                onChange={(value) => {
                  setUrl(value);
                  if (urlTouched && !value) setUrlTouched(false);
                }}
              />
              <ScrapeLimits value={limits} onChange={setLimits} />
            </div>
            <Button
              type="submit"
              className="w-full sm:w-auto"
              disabled={!url.trim() || working}
            >
              <Globe2 data-icon="inline-start" aria-hidden="true" />
              Analyze job board
            </Button>
          </form>
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
