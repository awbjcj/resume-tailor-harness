import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { api, unwrap } from "@/lib/api/client";
import type { Draft } from "./use-scrape";
import { ScrapeImport } from "./ScrapeImport";

export function ScrapeSourceHistory({ source }: { source: Draft }) {
  const [open, setOpen] = useState(false);
  const [revision, setRevision] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const cache = useQueryClient();
  const query = useQuery({
    queryKey: ["scrape-revisions", source.sourceId, source.revision],
    enabled: open,
    queryFn: () =>
      unwrap(
        api.GET("/api/scrape/sources/{source_id}/revisions", {
          params: { path: { source_id: source.sourceId } },
        }),
      ),
  });
  async function change(call: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    try {
      await call();
      await cache.invalidateQueries({ queryKey: ["scrape-sources"] });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <details
      className="w-full text-sm"
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary className="cursor-pointer">Source settings and history</summary>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <ScrapeImport initialUrl={source.url} label="Relearn page structure" />
        <Button
          variant="secondary"
          disabled={busy || source.state !== "approved"}
          onClick={() =>
            void change(() =>
              unwrap(
                api.PATCH("/api/scrape/sources/{source_id}", {
                  params: { path: { source_id: source.sourceId } },
                  body: {
                    expectedRevision: source.revision ?? 0,
                    enabled: source.enabled === false,
                  },
                }),
              ),
            )
          }
        >
          {source.enabled === false ? "Enable" : "Disable"}
        </Button>
        <label>
          Saved revision
          <select
            className="ml-2 rounded border bg-background p-2"
            aria-label="Saved revision"
            value={revision}
            onChange={(event) => setRevision(event.target.value)}
          >
            <option value="">Select revision</option>
            {query.data
              ?.filter((item) => item.revision !== source.revision)
              .map((item) => (
                <option key={item.revision} value={item.revision}>
                  {item.revision}
                </option>
              ))}
          </select>
        </label>
        <Button
          variant="secondary"
          disabled={busy || !revision}
          onClick={() =>
            void change(() =>
              unwrap(
                api.POST("/api/scrape/sources/{source_id}/rollback", {
                  params: { path: { source_id: source.sourceId } },
                  body: {
                    expectedRevision: source.revision ?? 0,
                    revision: Number(revision),
                  },
                }),
              ),
            )
          }
        >
          Restore revision
        </Button>
        {(error || query.error) && (
          <p role="alert" className="w-full text-destructive">
            {error || query.error?.message}
          </p>
        )}
      </div>
    </details>
  );
}
