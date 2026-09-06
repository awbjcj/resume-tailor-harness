import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { ScrapeJobEditor } from "@/features/sources/scrape/ScrapeJobEditor";
import type { JobFacts } from "@/features/sources/scrape/use-scrape";
import { api, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

type Override = components["schemas"]["OverrideOut"];
function CorrectionEditor({
  jobId,
  initial,
  overrides,
}: {
  jobId: number;
  initial: JobFacts;
  overrides: Override[];
}) {
  const [value, setValue] = useState(initial);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const cache = useQueryClient();
  async function save() {
    setBusy(true);
    setError("");
    try {
      for (const [key, next] of Object.entries(value)) {
        if (
          JSON.stringify(next) ===
            JSON.stringify(initial[key as keyof JobFacts]) ||
          ["sourceUrl", "postingId"].includes(key)
        )
          continue;
        const field = key.replace(
          /[A-Z]/g,
          (c) => `_${c.toLowerCase()}`,
        ) as Override["field"];
        await unwrap(
          api.PUT("/api/jobs/{job_id}/source-overrides/{field}", {
            params: { path: { job_id: jobId, field } },
            body: {
              field,
              value: next,
              expectedRevision:
                overrides.find((item) => item.field === field)?.revision ?? 0,
            },
          }),
        );
      }
      await cache.invalidateQueries({
        queryKey: ["source-observations", jobId],
      });
      await cache.invalidateQueries({ queryKey: ["source-overrides", jobId] });
      await cache.invalidateQueries({ queryKey: ["job", jobId] });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="space-y-3">
      <ScrapeJobEditor value={value} onChange={setValue} />
      <Button disabled={busy} onClick={() => void save()}>
        Save corrections
      </Button>
      {overrides
        .filter((item) => !item.removed)
        .map((item) => (
          <div key={item.field} className="flex items-center gap-2 text-sm">
            <span>{item.field}</span>
            <Button
              variant="ghost"
              disabled={busy}
              onClick={async () => {
                try {
                  await unwrap(
                    api.DELETE("/api/jobs/{job_id}/source-overrides/{field}", {
                      params: {
                        path: { job_id: jobId, field: item.field },
                        query: { expected_revision: item.revision },
                      },
                    }),
                  );
                  await cache.invalidateQueries({
                    queryKey: ["source-observations", jobId],
                  });
                  await cache.invalidateQueries({
                    queryKey: ["source-overrides", jobId],
                  });
                  await cache.invalidateQueries({ queryKey: ["job", jobId] });
                } catch (e) {
                  setError((e as Error).message);
                }
              }}
            >
              Use source value
            </Button>
          </div>
        ))}
      {error && (
        <p role="alert" className="text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}

export function SourceCorrections({ jobId }: { jobId: number }) {
  const [open, setOpen] = useState(false);
  const observations = useQuery({
    queryKey: ["source-observations", jobId],
    enabled: open,
    queryFn: () =>
      unwrap(
        api.GET("/api/jobs/{job_id}/source-observations", {
          params: { path: { job_id: jobId } },
        }),
      ),
  });
  const overrides = useQuery({
    queryKey: ["source-overrides", jobId],
    enabled: open && !!observations.data?.length,
    queryFn: () =>
      unwrap(
        api.GET("/api/jobs/{job_id}/source-overrides", {
          params: { path: { job_id: jobId } },
        }),
      ),
  });
  const latest = observations.data?.at(-1);
  return (
    <section className="space-y-3">
      <Button variant="outline" size="sm" onClick={() => setOpen((v) => !v)}>
        Review source fields
      </Button>
      {open && (
        <>
          {observations.error && (
            <p role="alert">{observations.error.message}</p>
          )}
          {observations.data?.length === 0 && (
            <p>No public-page extraction evidence is saved for this job.</p>
          )}
          {latest && (
            <details>
              <summary>Source evidence</summary>
              {latest.evidence?.map((item, i) => (
                <blockquote
                  key={i}
                  className="my-2 whitespace-pre-wrap text-sm text-muted-foreground"
                >
                  {item.field}: {item.quote}
                </blockquote>
              ))}
            </details>
          )}
          {latest && overrides.data && (
            <CorrectionEditor
              key={`${jobId}:${JSON.stringify(overrides.data)}`}
              jobId={jobId}
              initial={latest.facts}
              overrides={overrides.data}
            />
          )}
        </>
      )}
    </section>
  );
}
