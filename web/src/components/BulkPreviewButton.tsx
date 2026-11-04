import "@/i18n/interaction-copy-selection";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ConfirmDialog";

type BulkResult = { affected: number; skipped: number; reasons: Record<string, number> };

export function BulkPreviewButton({
  label,
  title,
  confirmLabel,
  variant = "outline",
  preview,
  run,
}: {
  label: string;
  title: string;
  confirmLabel?: string;
  variant?: "default" | "outline" | "destructive" | "secondary" | "ghost";
  preview: () => Promise<BulkResult>;
  run: () => Promise<BulkResult>;
}) {
  const { t } = useTranslation();
  const [result, setResult] = useState<BulkResult | null>(null);
  const [loading, setLoading] = useState(false);

  return (
    <ConfirmDialog
      trigger={
        <Button
          variant={variant}
          size="sm"
          onClick={() => {
            setResult(null);
            setLoading(true);
            preview()
              .then(setResult)
              .finally(() => setLoading(false));
          }}
        >
          {label}
        </Button>
      }
      title={title}
      description={
        loading || !result
          ? "Fetching preview count..."
          : t("interactionCopy.selection.preview", {
              affected: t("interactionCopy.selection.affected", {
                count: result.affected,
                formattedCount: result.affected.toLocaleString(),
              }),
              skipped: result.skipped
                ? ` · ${t("interactionCopy.selection.skipped", { count: result.skipped.toLocaleString() })}`
                : "",
            })
      }
      confirmLabel={confirmLabel ?? label}
      confirmDisabled={loading || !result}
      onConfirm={async () => {
        await run();
      }}
    />
  );
}
