import { useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { PencilLine, Save, Trash2 } from "lucide-react";
import "@/i18n/profile-changes";

import { ReviewCard } from "@/components/approval/ReviewCard";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import type { CoachDraftNote } from "./use-coach";

interface DraftNoteCardProps {
  note: CoachDraftNote;
  saving: boolean;
  discarding: boolean;
  busy?: boolean;
  onSave: (note: CoachDraftNote) => void | Promise<unknown>;
  onDiscard: () => void | Promise<unknown>;
}

export function DraftNoteCard({ note, saving, discarding, busy = false, onSave, onDiscard }: DraftNoteCardProps) {
  const { t } = useTranslation();
  const id = useId();
  const [editing, setEditing] = useState(false);
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const [title, setTitle] = useState(note.title);
  const [summary, setSummary] = useState(note.summary);
  const [decision, setDecision] = useState<"save" | "discard" | null>(null);
  const [failed, setFailed] = useState(false);
  const inFlight = useRef(false);
  const pending = note.status === "pending";
  const locked = busy || saving || discarding || decision !== null;
  const hasEvidence = Boolean(note.quotes?.some((quote) => quote.trim()));

  async function resolve(next: "save" | "discard") {
    if (locked || inFlight.current || !pending) return;
    if (next === "save" && (!title.trim() || !summary.trim() || !hasEvidence)) return;
    inFlight.current = true;
    setDecision(next);
    setFailed(false);
    try {
      if (next === "save") await onSave({ ...note, title: title.trim(), summary: summary.trim() });
      else await onDiscard();
      setEditing(false);
      setConfirmDiscard(false);
    } catch {
      setFailed(true);
    } finally {
      inFlight.current = false;
      setDecision(null);
    }
  }

  return (
    <ReviewCard title={pending ? title : note.title} status={pending ? t("profileChanges.pending") : note.status === "saved" ? t("profileChanges.note.saved") : t("profileChanges.discarded")}
      tone={pending ? "info" : note.status === "saved" ? "success" : "neutral"} busy={saving || discarding || decision !== null}
      description={t(pending ? "profileChanges.note.help" : note.status === "saved" ? "profileChanges.note.savedHelp" : "profileChanges.note.discardedHelp")}
      footer={pending ? <>
        {failed ? <p role="alert" className="text-sm leading-relaxed text-destructive">{t("profileChanges.failed")}</p> : null}
        {saving || discarding || decision ? <p role="status" className="text-sm text-muted-foreground">
          {t(saving || decision === "save" ? "profileChanges.note.saving" : "profileChanges.note.discarding")}
        </p> : null}
        {confirmDiscard ? <>
          <p className="text-sm leading-relaxed">{t("profileChanges.note.confirmDiscard")}</p>
          <div className="flex flex-col gap-2 @sm/review:flex-row @sm/review:flex-wrap">
            <Button className="h-auto min-h-11 whitespace-normal py-2" variant="outline" disabled={locked} onClick={() => setConfirmDiscard(false)}>{t("profileChanges.note.keep")}</Button>
            <Button className="h-auto min-h-11 whitespace-normal py-2" variant="destructive" disabled={locked} onClick={() => void resolve("discard")}>
              {discarding || decision === "discard" ? <Spinner data-icon="inline-start" /> : <Trash2 aria-hidden="true" />}
              {t("profileChanges.note.discard")}
            </Button>
          </div>
        </> : <div className="flex flex-col gap-2 @sm/review:flex-row @sm/review:flex-wrap">
          <Button className="h-auto min-h-11 whitespace-normal py-2" disabled={locked || !title.trim() || !summary.trim() || !hasEvidence} onClick={() => void resolve("save")}>
            {saving || decision === "save" ? <Spinner data-icon="inline-start" /> : <Save aria-hidden="true" />}
            {t("profileChanges.note.save")}
          </Button>
          <Button className="h-auto min-h-11 whitespace-normal py-2" variant="outline" disabled={locked} onClick={() => setEditing((value) => !value)}>
            <PencilLine aria-hidden="true" />{t(editing ? "profileChanges.note.preview" : "profileChanges.note.edit")}
          </Button>
          <Button className="h-auto min-h-11 whitespace-normal py-2" variant="ghost" disabled={locked} onClick={() => setConfirmDiscard(true)}>
            <Trash2 aria-hidden="true" />{t("profileChanges.note.discard")}
          </Button>
        </div>}
      </> : undefined}>
      <div className="min-w-0 space-y-4 p-4 sm:p-5">
        {editing && pending ? <>
          <Field>
            <FieldLabel htmlFor={`${id}-title`}>{t("profileChanges.note.title")}</FieldLabel>
            <Input id={`${id}-title`} value={title} required disabled={locked} onChange={(event) => setTitle(event.target.value)} />
          </Field>
          <Field>
            <FieldLabel htmlFor={`${id}-summary`}>{t("profileChanges.note.summary")}</FieldLabel>
            <Textarea id={`${id}-summary`} value={summary} rows={4} required disabled={locked} aria-describedby={`${id}-help`} onChange={(event) => setSummary(event.target.value)} />
            <FieldDescription id={`${id}-help`}>{t("profileChanges.note.summaryHelp")}</FieldDescription>
          </Field>
        </> : <p className="whitespace-pre-wrap text-sm leading-relaxed [overflow-wrap:anywhere]">{pending ? summary : note.summary}</p>}
        <div className="min-w-0 space-y-2 border-t pt-4">
          <p className="text-xs font-medium text-muted-foreground">{t("profileChanges.note.evidence")}</p>
          {hasEvidence ? (note.quotes ?? []).map((quote, index) => (
            <blockquote key={index} className="border-l-2 pl-3 text-sm leading-relaxed [overflow-wrap:anywhere]">{quote}</blockquote>
          )) : <p className="text-sm leading-relaxed text-muted-foreground">{t("profileChanges.note.noEvidence")}</p>}
        </div>
      </div>
    </ReviewCard>
  );
}
