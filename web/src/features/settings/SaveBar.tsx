import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { useUnsavedChanges } from "@/hooks/use-unsaved-changes";

export function SaveBar({
  dirty,
  saving,
  canSave = true,
  sticky = true,
  onSave,
  onDiscard,
}: {
  dirty: boolean;
  saving: boolean;
  canSave?: boolean;
  onSave: () => void;
  onDiscard: () => void;
  sticky?: boolean;
}) {
  useUnsavedChanges(dirty, saving);
  if (!dirty) return null;
  return (
    <div
      aria-label="Unsaved changes"
      className={`${sticky ? "sticky bottom-[max(1rem,env(safe-area-inset-bottom))] z-10" : "relative"} mt-2 flex flex-wrap items-center gap-3 rounded-lg border bg-background p-3 shadow-sm`}
    >
      <span role="status" className="text-sm text-muted-foreground">
        You have unsaved changes
      </span>
      <div className="ml-auto flex max-w-full flex-wrap gap-2">
        <Button type="button" variant="outline" onClick={onDiscard} disabled={saving}>
          Discard
        </Button>
        <Button type="button" onClick={onSave} disabled={saving || !canSave}>
          {saving ? <Spinner data-icon="inline-start" /> : null}
          Save changes
        </Button>
      </div>
    </div>
  );
}
