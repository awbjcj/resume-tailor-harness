import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { api, unwrap } from "@/lib/api/client";
import { ScrapeJobEditor } from "./ScrapeJobEditor";
import { ScrapeLimits } from "./ScrapeLimits";
import { ScrapeRuleEditor } from "./ScrapeRuleEditor";
import {
  defaultLimits,
  useScrapeDraft,
  type ApprovalResult,
  type Draft,
  type JobFacts,
} from "./use-scrape";

function DraftEditor({
  draft,
  onApproved,
  onValidate,
}: {
  draft: Draft & { id: string };
  onApproved: (result: ApprovalResult) => void;
  onValidate: (id: string, revision: number) => void;
}) {
  const cache = useQueryClient();
  const [revision, setRevision] = useState(draft.revision ?? 0);
  const [plan, setPlan] = useState(draft.plan);
  const [rulesChanged, setRulesChanged] = useState(false);
  const [limits, setLimits] = useState(draft.limits ?? defaultLimits);
  const [samples, setSamples] = useState<Record<string, JobFacts>>(() =>
    Object.fromEntries(
      (draft.samples ?? [])
        .filter((v) => v.jobKey)
        .map((v) => [v.jobKey!, v.facts]),
    ),
  );
  const [selected, setSelected] = useState(() => new Set(Object.keys(samples)));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const save = () =>
    unwrap(
      api.PATCH("/api/scrape/drafts/{draft_id}", {
        params: { path: { draft_id: draft.id } },
        body: {
          expectedRevision: revision,
          limits,
          samples,
          ...(rulesChanged ? { plan } : {}),
        },
      }),
    );
  async function act(approve: boolean) {
    setBusy(true);
    setError("");
    try {
      const saved = await save();
      setRevision(saved.revision ?? 0);
      if (approve)
        onApproved(
          await unwrap(
            api.POST("/api/scrape/drafts/{draft_id}/approve", {
              params: { path: { draft_id: draft.id } },
              body: {
                expectedRevision: saved.revision ?? 0,
                selectedKeys: [...selected],
              },
            }),
          ),
        );
      else {
        cache.setQueryData(["scrape-draft", draft.id], saved);
        onValidate(saved.id ?? draft.id, saved.revision ?? 0);
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="space-y-5">
      <p className="break-all text-sm text-muted-foreground">{draft.url}</p>
      <p className="text-sm">
        Review these sample jobs and their evidence. Corrections stay with each
        job; extraction rules are reused for future pulls.
      </p>
      {draft.navigation && (
        <div className="rounded-lg border bg-muted/25 p-3 text-sm" role="status">
          <p className="font-medium">
            Navigation outcome: {draft.navigation.terminalReason.replaceAll("_", " ")}
          </p>
          <p className="text-muted-foreground">
            {draft.navigation.discovered ?? 0} discovered ·{" "}
            {draft.navigation.inspected ?? 0} inspected
          </p>
          {(draft.navigation.messages ?? []).map((message, index) => (
            <p key={index} className="text-muted-foreground">
              {message}
            </p>
          ))}
        </div>
      )}
      <ScrapeLimits value={limits} onChange={setLimits} />
      {plan && (
        <ScrapeRuleEditor
          snapshotIds={[
            ...new Set(
              (draft.samples ?? []).flatMap((sample) =>
                (sample.evidence ?? []).map((item) => item.snapshotId),
              ),
            ),
          ]}
          plan={plan}
          onChange={(value) => {
            setPlan(value);
            setRulesChanged(true);
          }}
        />
      )}
      {(draft.samples ?? []).map((sample, index) => (
        <section key={sample.id} className="space-y-3 rounded-lg border p-4">
          <label className="flex gap-2 font-medium">
            <input
              type="checkbox"
              disabled={!sample.jobKey}
              checked={!!sample.jobKey && selected.has(sample.jobKey)}
              onChange={(event) =>
                setSelected((current) => {
                  const next = new Set(current);
                  if (event.target.checked) next.add(sample.jobKey!);
                  else next.delete(sample.jobKey!);
                  return next;
                })
              }
            />
            {sample.facts.title ?? `Sample ${index + 1}`}
          </label>
          {(sample.issues ?? []).map((issue, i) => (
            <p key={i} className="text-sm text-amber-700">
              {issue.field}: {issue.message || issue.kind}
            </p>
          ))}
          {sample.jobKey && (
            <ScrapeJobEditor
              value={samples[sample.jobKey]}
              onChange={(value) =>
                setSamples((current) => ({
                  ...current,
                  [sample.jobKey!]: value,
                }))
              }
            />
          )}
          <details>
            <summary className="cursor-pointer text-sm">
              Source evidence
            </summary>
            <dl className="mt-2 space-y-2 text-sm">
              {(sample.evidence ?? []).map((item, i) => (
                <div key={i}>
                  <dt className="font-medium">{item.field}</dt>
                  <dd className="whitespace-pre-wrap break-words text-muted-foreground">
                    {item.quote}
                  </dd>
                </div>
              ))}
            </dl>
          </details>
        </section>
      ))}
      {!draft.samples?.length && (
        <p>
          No verified job samples are available. This source cannot be approved
          yet.
        </p>
      )}
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        <Button
          variant="secondary"
          disabled={busy}
          onClick={() => void act(false)}
        >
          Save and validate rules
        </Button>
        <Button
          disabled={
            busy ||
            rulesChanged ||
            !draft.validation?.valid ||
            !draft.samples?.length
          }
          onClick={() => void act(true)}
        >
          Approve and save
        </Button>
      </div>
    </div>
  );
}

export function ScrapePreview({
  draftId,
  onApproved,
  onValidate,
}: {
  draftId: string;
  onApproved: (result: ApprovalResult) => void;
  onValidate: (id: string, revision: number) => void;
}) {
  const query = useScrapeDraft(draftId);
  if (query.error) return <p role="alert">{query.error.message}</p>;
  if (!query.data) return <p>Loading extraction preview…</p>;
  return (
    <DraftEditor
      key={`${draftId}:${query.data.revision}`}
      draft={{ ...query.data, id: draftId }}
      onApproved={onApproved}
      onValidate={onValidate}
    />
  );
}
