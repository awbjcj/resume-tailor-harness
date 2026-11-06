import "@/i18n/interaction-copy-selection";
import { Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";

import { ConfirmDialog } from "@/components/ConfirmDialog";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";

/**
 * Select-all plus the destructive bulk action, shared by the resume-version
 * and cover-letter tabs. Rendered only when something is actually deletable,
 * so a job with a single applied artifact shows no cleanup affordance at all.
 */
export function ArtifactSelectionBar({
  kind,
  selectedCount,
  allSelected,
  onToggleAll,
  onDelete,
  disabled,
}: {
  kind: "version" | "coverLetter";
  selectedCount: number;
  allSelected: boolean;
  onToggleAll: () => void;
  onDelete: () => void;
  disabled?: boolean;
}) {
  const { t } = useTranslation();
  const version = kind === "version";

  return (
    <div className="mt-3 flex flex-wrap items-center justify-between gap-3 rounded-xl border bg-muted/20 px-3 py-2">
      <label className="flex items-center gap-2 text-sm text-muted-foreground">
        <Checkbox
          checked={allSelected}
          disabled={disabled}
          onCheckedChange={onToggleAll}
          aria-label={t(version ? "interactionCopy.selection.selectVersions" : "interactionCopy.selection.selectLetters")}
        />
        {selectedCount > 0 ? t("interactionCopy.selection.count", { count: selectedCount }) : "Select all"}
      </label>
      <ConfirmDialog
        trigger={
          <Button
            size="sm"
            variant="destructive"
            disabled={disabled || selectedCount === 0}
          >
            <Trash2 data-icon="inline-start" />
            {selectedCount > 0
              ? t("interactionCopy.selection.deleteSelectedCount", { count: selectedCount })
              : t("interactionCopy.selection.deleteSelected")}
          </Button>
        }
        title={t(version ? "interactionCopy.selection.deleteVersion" : "interactionCopy.selection.deleteLetter", { count: selectedCount })}
        description={t(version ? "interactionCopy.selection.versionDescription" : "interactionCopy.selection.letterDescription", { count: selectedCount })}
        confirmLabel="Confirm delete"
        onConfirm={onDelete}
      />
    </div>
  );
}
