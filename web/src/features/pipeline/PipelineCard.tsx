import type { ReactNode } from "react";

import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { StatusBadge } from "@/components/StatusBadge";
import { FitMeter } from "@/components/FitMeter";
import type { PipelineItem } from "./use-pipeline";

export function PipelineCard({
  row,
  onOpen,
  selected,
  onSelect,
  footer,
}: {
  row: PipelineItem;
  onOpen: () => void;
  selected?: boolean;
  onSelect?: (checked: boolean) => void;
  footer?: ReactNode;
}) {
  return (
    <Card data-selected={selected ?? false} className="board-job-card min-w-0 flex-col gap-4 rounded-xl p-4 sm:p-5">
      <div className="flex items-start gap-3">
        {onSelect && (
          <div className="pt-1">
            <Checkbox
              checked={selected}
              onCheckedChange={(value) => onSelect(Boolean(value))}
              aria-label={`Select ${row.company ?? "job"} ${row.title ?? ""}`.trim()}
            />
          </div>
        )}
        <button
          type="button"
          onClick={onOpen}
          className="group block min-w-0 flex-1 rounded-md text-left outline-none focus-visible:ring-3 focus-visible:ring-ring/40"
        >
          <div className="flex items-start gap-3">
            <FitMeter score={row.fitScore} />
            <div className="min-w-0 flex-1">
              <div className="break-words text-lg font-semibold leading-snug group-hover:text-primary">
                {row.title ?? "—"}
              </div>
              <div className="mt-1 text-sm text-muted-foreground">{row.company ?? "—"}</div>
              <div className="mt-2.5"><StatusBadge status={row.status} /></div>
            </div>
          </div>
          <p className="mt-4 line-clamp-3 break-words whitespace-pre-line text-sm leading-6 text-muted-foreground [overflow-wrap:anywhere]">
            {row.jdPreview}
          </p>
        </button>
      </div>
      {footer && <div className="mt-auto flex flex-wrap justify-end gap-1 border-t pt-3">{footer}</div>}
    </Card>
  );
}
