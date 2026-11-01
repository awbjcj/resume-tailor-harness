import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle, Check, ChevronDown, Loader2 } from "lucide-react";
import "@/i18n/profile-changes";

import { ChangePreview } from "@/components/approval/ChangePreview";
import { ConfirmChangesDialog } from "@/components/approval/ConfirmChangesDialog";
import { ReviewCard } from "@/components/approval/ReviewCard";
import { Button } from "@/components/ui/button";
import { localizeReviewField } from "@/i18n/review-fields";
import { ApiError } from "@/lib/api/client";
import type { CoachChangeDraft } from "./use-coach";

const INTERNAL_FIELDS = new Set([
  "id", "source", "source_ref", "source_refs", "schema_version", "synthesized", "inferred",
  "evidence_fact_ids", "github_profile", "extra",
]);

function previewName(value: unknown) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return undefined;
  const record = value as Record<string, unknown>;
  return [record.name, record.title, record.question].find((item): item is string => typeof item === "string" && Boolean(item.trim()));
}

export function ProfileChangeCard({ draft, busy, onResolve }: {
  draft: CoachChangeDraft;
  busy: boolean;
  onResolve: (decision: "apply" | "discard") => void | Promise<unknown>;
}) {
  const { t, i18n } = useTranslation();
  const [decision, setDecision] = useState<"apply" | "discard" | null>(null);
  const [failure, setFailure] = useState<"conflict" | "failed" | null>(null);
  const [confirming, setConfirming] = useState(false);
  const inFlight = useRef(false);
  const applyRef = useRef<HTMLButtonElement>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const pending = draft.status === "pending";
  const disabled = busy || decision !== null;
  const removals = (draft.previews ?? []).filter((preview) => preview.operation === "delete");
  const previewTitle = (preview: NonNullable<CoachChangeDraft["previews"]>[number]) => {
    const entity = localizeReviewField(preview.entity, i18n.resolvedLanguage);
    const operation = t(`profileChanges.operations.${preview.operation}`, { defaultValue: "" });
    return i18n.resolvedLanguage?.startsWith("zh") ? `${operation}${entity}` : `${operation} ${entity.toLowerCase()}`;
  };

  async function resolve(next: "apply" | "discard") {
    if (disabled || inFlight.current || !pending || (next === "apply" && failure === "conflict")) return;
    inFlight.current = true;
    setDecision(next);
    setFailure(null);
    try {
      await onResolve(next);
      setConfirming(false);
      cardRef.current?.focus({ preventScroll: true });
    } catch (cause) {
      setFailure(cause instanceof ApiError && cause.code.includes("CONFLICT") ? "conflict" : "failed");
    } finally {
      inFlight.current = false;
      setDecision(null);
    }
  }

  return <>
    <ReviewCard focusRef={cardRef} title={draft.title} description={pending ? t("profileChanges.help") : undefined}
      status={t(`profileChanges.${draft.status}`)} tone={pending ? "info" : draft.status === "applied" ? "success" : "neutral"} busy={decision !== null}
      footer={pending ? <>
        {decision ? <p role="status" className="text-sm text-muted-foreground">{t(decision === "apply" ? "profileChanges.saving" : "profileChanges.discarding")}</p> : null}
        {failure && !confirming ? <p role="alert" className="text-sm leading-relaxed text-destructive">{t(`profileChanges.${failure}`)}</p> : null}
        <div className="flex flex-col gap-2 @sm/review:flex-row @sm/review:flex-wrap">
          <Button ref={applyRef} className="h-auto min-h-11 whitespace-normal py-2" disabled={disabled || failure === "conflict"}
            onClick={() => removals.length ? setConfirming(true) : void resolve("apply")}>
            {decision === "apply" ? <Loader2 className="motion-safe:animate-spin" aria-hidden="true" /> : <Check aria-hidden="true" />}
            {t("profileChanges.apply")}
          </Button>
          <Button className="h-auto min-h-11 whitespace-normal py-2" variant="outline" disabled={disabled} onClick={() => void resolve("discard")}>
            {decision === "discard" ? <Loader2 className="motion-safe:animate-spin" aria-hidden="true" /> : null}
            {t("profileChanges.discard")}
          </Button>
        </div>
      </> : undefined}>
      <details className="group/profile min-w-0 p-4 sm:p-5" open={pending}>
        <summary className="flex min-h-11 cursor-pointer items-center gap-2 rounded-md text-sm font-medium outline-none focus-visible:ring-2 focus-visible:ring-ring [&::-webkit-details-marker]:hidden">
          <ChevronDown className="size-4 shrink-0 -rotate-90 group-open/profile:rotate-0" aria-hidden="true" />
          {t("profileChanges.details")}
        </summary>
        <div className="min-w-0 space-y-4 pt-2">
          {(draft.previews ?? []).map((preview, index) => <section key={index} className="min-w-0 space-y-3">
            <h4 className="text-sm font-semibold [overflow-wrap:anywhere]">{previewTitle(preview)}</h4>
            {preview.entity === "profile" && preview.operation === "delete" ? <p className="flex items-start gap-2 text-sm leading-relaxed text-destructive">
              <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />{t("profileChanges.removalHelp")}
            </p> : null}
            <ChangePreview before={preview.before} after={preview.after} hiddenFields={INTERNAL_FIELDS} entity={preview.entity} />
          </section>)}
          {draft.quotes?.length ? <div className="space-y-2 border-t pt-4">
            <p className="text-xs font-medium text-muted-foreground">{t("profileChanges.evidence")}</p>
            {draft.quotes.map((quote, index) => <blockquote key={index} className="border-l-2 pl-3 text-sm leading-relaxed [overflow-wrap:anywhere]">{quote}</blockquote>)}
          </div> : null}
        </div>
      </details>
    </ReviewCard>
    <ConfirmChangesDialog open={confirming} onOpenChange={setConfirming}
      title={t("profileChanges.confirmTitle")} description={t("profileChanges.confirmHelp")}
      confirmLabel={t("profileChanges.confirmAction")} cancelLabel={t("profileChanges.cancel")}
      busy={decision !== null} disabled={busy || !pending || failure === "conflict"} onConfirm={() => void resolve("apply")}
      finalFocus={() => applyRef.current ?? cardRef.current} error={failure ? t(`profileChanges.${failure}`) : undefined}>
      <ul className="space-y-2 text-sm">{removals.map((preview, index) => <li key={index} className="min-w-0 space-y-1 [overflow-wrap:anywhere]">
        <p className="font-medium">{previewTitle(preview)}</p>
        {previewName(preview.before) ? <p className="text-muted-foreground">{previewName(preview.before)}</p> : null}
      </li>)}</ul>
    </ConfirmChangesDialog>
  </>;
}
