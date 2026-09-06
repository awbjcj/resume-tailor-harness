import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, unwrap } from "@/lib/api/client";
import { useLaunchRun } from "./use-launch-run";
import { ScrapeImport } from "@/features/sources/scrape/ScrapeImport";

export function AddUrlDialog() {
  const [url, setUrl] = useState("");
  const [open, setOpen] = useState(false);
  const { launch } = useLaunchRun();
  const [runId, setRunId] = useState("");
  const run = useQuery({
    queryKey: ["add-url-run", runId],
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
  const result = run.data?.result;
  const draftId =
    result &&
    typeof result === "object" &&
    "draftId" in result &&
    typeof result.draftId === "string"
      ? result.draftId
      : "";
  const working =
    !!runId &&
    !["done", "error", "cancelled"].includes(run.data?.state ?? "pending");

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger
        render={
          <Button variant="outline" size="sm">
            + Add URL
          </Button>
        }
      />
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add job by URL</DialogTitle>
        </DialogHeader>
        <Label htmlFor="add-url">Job posting URL</Label>
        <Input
          id="add-url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://…"
        />
        <Button
          disabled={!url.trim() || working}
          onClick={async () => {
            const launched = await launch("addJobUrl", async () => {
              const value = await unwrap(
                api.POST("/api/jobs/from-url", {
                  body: { url, allowBrowser: true, publicExtraction: true },
                }),
              );
              setRunId(value.runId);
              return value;
            });
            if (!launched) return;
          }}
        >
          Add job
        </Button>
        {working && (
          <p role="status">{run.data?.label || "Inspecting public page…"}</p>
        )}
        {run.data?.error && <p role="alert">{run.data.error}</p>}
        {run.data?.state === "done" && !draftId && (
          <p role="status">Imported</p>
        )}
        <ScrapeImport
          key={draftId || url}
          initialUrl={url}
          initialDraftId={draftId}
          label="Preview public page"
        />
      </DialogContent>
    </Dialog>
  );
}
