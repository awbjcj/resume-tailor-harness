import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "@/lib/api/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { BoardPlan } from "./use-scrape";

export function ScrapeRuleEditor({
  plan,
  onChange,
  snapshotIds = [],
}: {
  plan: BoardPlan;
  onChange: (plan: BoardPlan) => void;
  snapshotIds?: string[];
}) {
  return (
    <details className="rounded border p-3">
      <summary className="cursor-pointer text-sm font-medium">
        Change extraction rules
      </summary>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        {(
          [
            ["cardSelector", "Job card selector"],
            ["detailSelector", "Description selector"],
            ["linkSelector", "Job link selector"],
            ["openSelector", "Open detail selector"],
            ["closeSelector", "Close detail selector"],
            ["controlSelector", "Next results selector"],
          ] as const
        ).map(([field, label]) => (
          <label key={field} className="text-sm">
            {label}
            <Input
              value={plan[field] ?? ""}
              onChange={(event) =>
                onChange({ ...plan, [field]: event.target.value || null })
              }
            />
          </label>
        ))}
        {(plan.fieldRules ?? []).map((rule, index) => (
          <label key={index} className="text-sm">
            {rule.field}
            <Input
              aria-label={`Selector for ${rule.field}`}
              value={rule.selector}
              onChange={(event) =>
                onChange({
                  ...plan,
                  fieldRules: plan.fieldRules?.map((item, i) =>
                    i === index
                      ? { ...item, selector: event.target.value }
                      : item,
                  ),
                })
              }
            />
          </label>
        ))}
      </div>
      {snapshotIds.length > 0 && (
        <ElementPicker
          snapshotIds={snapshotIds}
          plan={plan}
          onChange={onChange}
        />
      )}
    </details>
  );
}

function ElementPicker({
  snapshotIds,
  plan,
  onChange,
}: {
  snapshotIds: string[];
  plan: BoardPlan;
  onChange: (plan: BoardPlan) => void;
}) {
  const [snapshotId, setSnapshotId] = useState(snapshotIds[0]);
  const [field, setField] =
    useState<NonNullable<BoardPlan["fieldRules"]>[number]["field"]>("jd_text");
  const [selector, setSelector] = useState("");
  const query = useQuery({
    queryKey: ["scrape-elements", snapshotId],
    queryFn: () =>
      unwrap(
        api.GET("/api/scrape/snapshots/{snapshot_id}/elements", {
          params: { path: { snapshot_id: snapshotId } },
        }),
      ),
  });
  return (
    <div className="mt-4 space-y-2 border-t pt-3">
      <p className="text-sm">Choose observed page content for a field.</p>
      <label className="block text-sm">
        Source snapshot
        <select
          className="block w-full rounded border bg-background p-2"
          value={snapshotId}
          onChange={(e) => {
            setSnapshotId(e.target.value);
            setSelector("");
          }}
        >
          {snapshotIds.map((id, i) => (
            <option key={id} value={id}>
              {i + 1}
            </option>
          ))}
        </select>
      </label>
      <label className="block text-sm">
        Field
        <select
          className="block w-full rounded border bg-background p-2"
          value={field}
          onChange={(e) => setField(e.target.value as typeof field)}
        >
          {(
            [
              ["title", "Title"],
              ["company", "Company"],
              ["jd_text", "Full description"],
              ["locations", "Locations"],
              ["remote_restrictions", "Remote geographic restrictions"],
              ["attendance", "Office attendance"],
              ["employment_type", "Employment type"],
              ["posted_at", "Posted date"],
              ["closes_at", "Closing date"],
            ] as const
          ).map(([name, label]) => (
            <option key={name} value={name}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <label className="block text-sm">
        Observed content
        <select
          className="block w-full min-w-0 rounded border bg-background p-2"
          value={selector}
          onChange={(e) => setSelector(e.target.value)}
        >
          <option value="">Select content</option>
          {query.data?.map((item) => (
            <option key={item.selector} value={item.selector}>
              {item.text.slice(0, 140)}
            </option>
          ))}
        </select>
      </label>
      {query.error && <p role="alert">{query.error.message}</p>}
      <Button
        variant="secondary"
        disabled={!selector}
        onClick={() =>
          onChange({
            ...plan,
            ...(field === "jd_text" ? { detailSelector: selector } : {}),
            fieldRules: [
              ...(plan.fieldRules ?? []).filter((rule) => rule.field !== field),
              { field, selector },
            ],
          })
        }
      >
        Use selected content
      </Button>
    </div>
  );
}
