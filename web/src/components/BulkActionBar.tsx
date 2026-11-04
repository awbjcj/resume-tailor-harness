import "@/i18n/interaction-copy-selection";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";

export function BulkActionBar({
  count,
  isAllMatching,
  pageCount,
  total,
  onSelectAllMatching,
  onClear,
  children,
}: {
  count: number;
  isAllMatching: boolean;
  pageCount: number;
  total: number;
  onSelectAllMatching: () => void;
  onClear: () => void;
  children: ReactNode;
}) {
  const { t } = useTranslation();
  if (count === 0) return null;
  return (
    <div className="mb-4 rounded-lg border bg-card shadow-sm">
      <div className="flex flex-wrap items-center gap-2 p-3">
        <span
          role="status"
          aria-label={t("interactionCopy.selection.count", { count: count.toLocaleString() })}
          className="rounded-full bg-secondary px-3 py-1 text-sm"
        >
          {t("interactionCopy.selection.count", { count: count.toLocaleString() })}
        </span>
        {children}
        <Button variant="ghost" size="sm" className="ml-auto" onClick={onClear}>
          Clear
        </Button>
      </div>
      {!isAllMatching && count === pageCount && total > pageCount && (
        <>
          <Separator />
          <div className="bg-primary/5 px-3 py-2 text-sm text-primary">
            {t("interactionCopy.selection.loaded", { count: pageCount.toLocaleString() })}{" "}
            <Button
              variant="link"
              size="sm"
              className="h-auto px-1 py-0"
              onClick={onSelectAllMatching}
            >
              {t("interactionCopy.selection.selectMatching", { count: total.toLocaleString() })}
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
