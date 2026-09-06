import { useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link2, Plus } from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { PublicUrlField, isPublicHttpUrl } from "@/components/PublicUrlField";
import { api, unwrap } from "@/lib/api/client";
import { useLaunchRun } from "./use-launch-run";
import { ScrapeImport } from "@/features/sources/scrape/ScrapeImport";

export function AddUrlDialog() {
  const [url, setUrl] = useState("");
  const [open, setOpen] = useState(false);
  const { launch } = useLaunchRun();
  const [runId, setRunId] = useState("");
  const [urlTouched, setUrlTouched] = useState(false);
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
  const urlIsValid = isPublicHttpUrl(url);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setUrlTouched(true);
    if (!urlIsValid || working) return;
    const launched = await launch("addJobUrl", async () => {
      const value = await unwrap(
        api.POST("/api/jobs/from-url", {
          body: {
            url: url.trim(),
            allowBrowser: true,
            publicExtraction: true,
          },
        }),
      );
      setRunId(value.runId);
      return value;
    });
    if (!launched) return;
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger
        render={
          <Button variant="outline" size="sm">
            <Plus data-icon="inline-start" aria-hidden="true" /> Add job URL
          </Button>
        }
      />
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Add job by URL</DialogTitle>
          <DialogDescription>
            Paste one public job posting. We’ll import its details and flag
            anything that needs your review.
          </DialogDescription>
        </DialogHeader>
        <form
          className="space-y-4"
          noValidate
          onSubmit={(event) => void submit(event)}
        >
          <div className="rounded-xl border bg-muted/25 p-4">
            <PublicUrlField
              id="add-url"
              label="Job posting URL"
              value={url}
              placeholder="https://company.com/jobs/role"
              invalid={urlTouched && !urlIsValid}
              onBlur={() => setUrlTouched(true)}
              onChange={(value) => {
                setUrl(value);
                if (urlTouched && !value) setUrlTouched(false);
              }}
            />
          </div>
          <DialogFooter>
            <Button type="submit" disabled={!url.trim() || working}>
              <Link2 data-icon="inline-start" aria-hidden="true" />
              {working ? "Importing job…" : "Add job"}
            </Button>
          </DialogFooter>
        </form>
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
