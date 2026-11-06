import "@/i18n/interaction-copy-redo";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Field,
  FieldContent,
  FieldDescription,
  FieldGroup,
  FieldLabel,
  FieldLegend,
  FieldSet,
} from "@/components/ui/field";
import { Spinner } from "@/components/ui/spinner";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";

import type { RedoRequest, RedoStage } from "./use-redo-run";

// Keep requests in pipeline order for readability.
const STAGES: { id: RedoStage; label: string; hint: string }[] = [
  {
    id: "pull",
    label: "Re-pull job description",
    hint: "Re-fetch the posting and replace its text.",
  },
  {
    id: "extract",
    label: "Re-extract criteria & fit score",
    hint: "Rebuild criteria and re-score against your profile.",
  },
  {
    id: "tailor",
    label: "Re-tailor resume",
    hint: "Create a new resume version.",
  },
  { id: "render", label: "Re-render PDF", hint: "Regenerate the PDF for the resume selected for the application. If none is selected, use the latest version." },
];

export interface RedoDialogProps {
  open: boolean;
  jobIds: number[];
  initialStages: RedoStage[];
  onOpenChange: (open: boolean) => void;
  onLaunch: (request: RedoRequest) => Promise<boolean>;
}

export function RedoDialog(props: RedoDialogProps) {
  // Same closed->open remount guard as LaunchDialog: Base UI's Dialog stays
  // mounted through its exit animation, so remounting mid-close strands an
  // already-open popup that never hides. Unlike LaunchDialog, jobIds isn't
  // seeded into any RedoDialogBody state (count/label read the prop live),
  // so it must NOT factor into resetKey -- callers like AttentionCard clear
  // their target (jobIds -> []) in the same update that closes the dialog,
  // and keying on jobIds.length would remount a fresh, already-closed body
  // right at that moment, stranding a stuck-open "0 jobs" popup whose
  // Cancel/Close call back into an already-cleared target and do nothing.
  const [openState, setOpenState] = useState(() => ({
    isOpen: props.open,
    sequence: 0,
  }));
  const [isLaunching, setIsLaunching] = useState(false);
  if (props.open !== openState.isOpen) {
    setOpenState({
      isOpen: props.open,
      sequence: props.open ? openState.sequence + 1 : openState.sequence,
    });
  }
  const resetKey = String(openState.sequence);
  const launch = async (request: RedoRequest) => {
    setIsLaunching(true);
    try {
      return await props.onLaunch(request);
    } finally {
      setIsLaunching(false);
    }
  };
  return (
    <Dialog open={props.open} onOpenChange={(open, details) => {
      if (isLaunching) details.cancel();
      else props.onOpenChange(open);
    }}>
      <RedoDialogBody key={resetKey} {...props} onLaunch={launch} isLaunching={isLaunching} />
    </Dialog>
  );
}

function RedoDialogBody({
  jobIds,
  initialStages,
  onOpenChange,
  onLaunch,
  isLaunching,
}: RedoDialogProps & { isLaunching: boolean }) {
  const { t } = useTranslation();
  const [selected, setSelected] = useState<Set<RedoStage>>(
    () => new Set(initialStages),
  );
  const [deep, setDeep] = useState(false);
  const [cleanupTargets, setCleanupTargets] = useState<string | null>(null);

  const ordered = STAGES.filter((stage) => selected.has(stage.id)).map((s) => s.id);
  const tailoring = selected.has("tailor");
  const count = jobIds.length;
  const targetKey = jobIds.join(",");
  if (cleanupTargets !== null && cleanupTargets !== targetKey) setCleanupTargets(null);
  const removePrevious = tailoring && cleanupTargets === targetKey;
  const jobCountText = t("interactionCopy.redo.jobCount", { count });
  const label = !ordered.length ? "Choose a stage" : removePrevious
    ? t("interactionCopy.redo.cleanupButton")
    : t("interactionCopy.redo.button", { jobs: jobCountText });

  const toggle = (stage: RedoStage, checked: boolean) => {
    if (stage === "tailor" && !checked) setCleanupTargets(null);
    setSelected((current) => {
      const next = new Set(current);
      if (checked) {
        next.add(stage);
        // A fresh posting usually needs new criteria, so preselect re-extract.
        if (stage === "pull") next.add("extract");
      } else {
        next.delete(stage);
      }
      return next;
    });
  };

  const submit = async () => {
    const request: RedoRequest = {
      jobIds, stages: ordered, deep: tailoring && deep,
      removePreviousVersions: removePrevious,
    };
    if (await onLaunch(request)) onOpenChange(false);
  };

  return (
    <DialogContent className="grid-cols-1 sm:max-w-lg" showCloseButton={!isLaunching}>
      <DialogHeader className="pr-9">
        <DialogTitle>Redo job stages</DialogTitle>
        <DialogDescription>
          {t("interactionCopy.redo.description", { jobs: jobCountText })}
        </DialogDescription>
      </DialogHeader>

      <FieldSet>
        <FieldLegend variant="label">Stages</FieldLegend>
        <FieldGroup>
          {STAGES.map((stage) => {
            const inputId = `redo-stage-${stage.id}`;
            return (
              <Field key={stage.id} orientation="horizontal">
                <Checkbox
                  id={inputId}
                  checked={selected.has(stage.id)}
                  disabled={isLaunching}
                  onCheckedChange={(checked) => toggle(stage.id, Boolean(checked))}
                />
                <FieldContent>
                  <FieldLabel htmlFor={inputId}>{stage.label}</FieldLabel>
                  <FieldDescription>
                    {stage.id === "render" && tailoring
                      ? t("interactionCopy.redo.renderNew")
                      : stage.hint}
                  </FieldDescription>
                </FieldContent>
              </Field>
            );
          })}
        </FieldGroup>
      </FieldSet>

      {tailoring && (
        <FieldGroup>
          <Field orientation="horizontal">
            <Switch
              id="redo-deep-review"
              checked={deep}
              disabled={isLaunching}
              onCheckedChange={setDeep}
            />
            <FieldContent>
              <FieldLabel htmlFor="redo-deep-review">Deep review</FieldLabel>
              <FieldDescription>Use the full review panel. This usually takes 3–6 times as long.</FieldDescription>
            </FieldContent>
          </Field>
          <Field orientation="horizontal" className="rounded-lg border bg-muted/30 p-3 data-[cleanup]:border-destructive/40" data-cleanup={removePrevious || undefined}>
            <Checkbox
              id="redo-remove-previous"
              aria-describedby="redo-remove-previous-hint"
              checked={removePrevious}
              disabled={isLaunching || count === 0}
              onCheckedChange={(checked) => setCleanupTargets(checked ? targetKey : null)}
            />
            <FieldContent>
              <FieldLabel htmlFor="redo-remove-previous">
                {t("interactionCopy.redo.removePrevious")}
              </FieldLabel>
              <FieldDescription id="redo-remove-previous-hint">
                {t("interactionCopy.redo.removePreviousHint")}
              </FieldDescription>
            </FieldContent>
          </Field>
        </FieldGroup>
      )}

      <DialogFooter>
        <Button
          variant="outline"
          className="min-h-11"
          disabled={isLaunching}
          onClick={() => onOpenChange(false)}
        >
          Cancel
        </Button>
        <Button
          variant={removePrevious ? "destructive" : "default"}
          className={cn(
            "h-auto min-h-11 max-w-full whitespace-normal py-2 transition-none",
            removePrevious && "border-destructive/30 bg-destructive/5 hover:bg-destructive/10 dark:bg-destructive/5 dark:hover:bg-destructive/10",
          )}
          aria-describedby={removePrevious ? "redo-remove-previous-hint" : undefined}
          disabled={!count || !ordered.length || isLaunching}
          onClick={submit}
        >
          {isLaunching && <Spinner data-icon="inline-start" aria-hidden="true" />}
          {isLaunching ? "Starting…" : label}
        </Button>
      </DialogFooter>
    </DialogContent>
  );
}
