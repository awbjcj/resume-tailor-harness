import { Trash2 } from "lucide-react";

import { ConfirmDialog } from "@/components/ConfirmDialog";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * The per-row destructive action for a resume version or cover letter.
 *
 * When the artifact is applied the button is disabled rather than hidden, and
 * its tooltip names the way out. Hiding it would leave the user hunting for a
 * delete that exists but is conditional; the API refuses this case with a 409
 * regardless, so the control's job is to explain the refusal before it happens.
 */
export function ArtifactDeleteButton({
  noun,
  label,
  showLabel,
  applied,
  disabled,
  onConfirm,
}: {
  noun: string;
  label: string;
  showLabel?: boolean;
  applied: boolean;
  disabled?: boolean;
  onConfirm: () => void;
}) {
  const trigger = (
    <Button
      size={showLabel ? "sm" : "icon-sm"}
      variant="ghost"
      className={cn("text-muted-foreground hover:text-destructive", showLabel && "max-sm:w-9 max-sm:px-0")}
      disabled={applied || disabled}
      aria-label={`Delete ${label}`}
      title={
        applied ? `Unselect this ${noun} to delete it` : `Delete ${label}`
      }
    >
      <Trash2 aria-hidden="true" />
      {showLabel && <span className="hidden sm:inline">Delete</span>}
    </Button>
  );

  // An applied artifact never opens the dialog — the trigger is inert, so the
  // confirm flow is not even reachable.
  if (applied || disabled) return trigger;

  return (
    <ConfirmDialog
      trigger={trigger}
      title={`Delete ${label}?`}
      description={`This ${noun} and its rendered PDF will be removed. This cannot be undone.`}
      confirmLabel="Confirm delete"
      onConfirm={onConfirm}
    />
  );
}
