import { useState } from "react";
import { ScrapePullStatus } from "./ScrapePullStatus";
import { ScrapeSourceHistory } from "./ScrapeSourceHistory";
import { Button } from "@/components/ui/button";
import { useLaunchRun } from "@/features/runs/use-launch-run";
import { api, unwrap } from "@/lib/api/client";
import { ScrapeImport } from "./ScrapeImport";
import { useScrapeSources } from "./use-scrape";

export function ScrapeSources() {
  const query = useScrapeSources();
  const { launch } = useLaunchRun();
  const [runIds, setRunIds] = useState<Record<string, string>>({});
  const [refresh, setRefresh] = useState<Record<string, boolean>>({});
  if (!query.data?.length) return null;
  return (
    <section className="space-y-3">
      <h2 className="text-sm font-semibold">Saved public boards</h2>
      {query.data.map((source) => (
        <article
          key={source.sourceId}
          className="flex min-w-0 flex-wrap items-center justify-between gap-3 rounded-lg border p-4"
        >
          <div className="min-w-0">
            <p className="break-all text-sm">{source.url}</p>
            <p className="text-xs text-muted-foreground">
              {source.state === "approved"
                ? "Approved revision"
                : "Needs review"}{" "}
              {source.revision} · {source.limits?.detailPages ?? 50} job details
              per pull
            </p>
          </div>
          <div className="flex gap-2">
            <ScrapeImport
              sourceId={source.sourceId}
              initialUrl={source.url}
              label="Edit or relearn"
            />
            <Button
              variant="secondary"
              disabled={source.state !== "approved" || source.enabled === false}
              onClick={() =>
                void launch(
                  "scrapePull",
                  async () => {
                    const run = await unwrap(
                      api.POST("/api/scrape/sources/{source_id}/pull", {
                        params: {
                          path: { source_id: source.sourceId },
                          query: { refresh: refresh[source.sourceId] ?? false },
                        },
                      }),
                    );
                    setRunIds((current) => ({
                      ...current,
                      [source.sourceId]: run.runId,
                    }));
                    return run;
                  },
                  ["triage", "scrape-sources"],
                )
              }
            >
              Re-pull
            </Button>
          </div>
          <label className="flex items-center gap-2 text-xs">
            <input
              type="checkbox"
              checked={refresh[source.sourceId] ?? false}
              onChange={(event) =>
                setRefresh((current) => ({
                  ...current,
                  [source.sourceId]: event.target.checked,
                }))
              }
            />
            Refresh cached pages
          </label>
          <ScrapeSourceHistory source={source} />
          <ScrapePullStatus runId={runIds[source.sourceId] ?? ""} />
        </article>
      ))}
    </section>
  );
}
