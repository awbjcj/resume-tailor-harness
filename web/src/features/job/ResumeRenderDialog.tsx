import { useId, useState } from "react";
import { FileText, Palette } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/ui/spinner";
import { useRenderTemplates } from "@/features/settings/use-render-templates";
import { ApiError } from "@/lib/api/client";
import { useRenderVersion } from "./use-job-mutations";

export function ResumeRenderDialog({
  jobId, versionId, templateId, pdfAvailable, applied, disabled,
}: {
  jobId: number;
  versionId: number;
  templateId?: string | null;
  pdfAvailable: boolean;
  applied: boolean;
  disabled: boolean;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [choice, setChoice] = useState<string | null>(null);
  const fieldId = useId();
  const templates = useRenderTemplates(open);
  const render = useRenderVersion(jobId);
  const selected = choice ?? templateId ?? "";
  const style = templates.data?.find((item) => item.id === selected);
  const loadingStyles = !templates.data && templates.isFetching;
  const errorCode = render.error instanceof ApiError ? render.error.code : undefined;
  const unavailable = Boolean(selected && (
    (templates.data && !style) ||
    (errorCode === "template_not_found" && render.variables?.templateId === selected)
  ));
  const canSubmit = !render.isPending && !loadingStyles && !unavailable;
  const hintId = `${fieldId}-hint`;

  return (
    <Dialog open={open} onOpenChange={(next, details) => {
      if (render.isPending) {
        details.cancel();
        return;
      }
      if (next) {
        setChoice(null);
        render.reset();
      }
      setOpen(next);
    }}>
      <DialogTrigger render={<Button size="sm" variant={pdfAvailable ? "outline" : "default"} disabled={disabled} />}>
        {pdfAvailable ? <Palette data-icon="inline-start" aria-hidden="true" /> : <FileText data-icon="inline-start" aria-hidden="true" />}
        {pdfAvailable ? "Change style" : "Render PDF"}
      </DialogTrigger>
      <DialogContent className="grid-cols-1 sm:max-w-md" showCloseButton={false}>
        <DialogHeader>
          <DialogTitle>{t("resumeVersions.renderTitle", { id: versionId })}</DialogTitle>
          <DialogDescription>
            {pdfAvailable
              ? applied
                ? "The new PDF will replace the one selected for your application."
                : "The new PDF will replace the current one for this version."
              : "Use the workspace default or choose a style for this PDF."}
          </DialogDescription>
        </DialogHeader>
        <form className="grid grid-cols-1 gap-4" onSubmit={(event) => {
          event.preventDefault();
          if (canSubmit) {
            render.mutate({ versionId, templateId: selected || undefined }, { onSuccess: () => setOpen(false) });
          }
        }}>
          <div className="grid grid-cols-1 gap-2">
            <Label htmlFor={fieldId}>Resume style</Label>
            <select
              id={fieldId}
              className="h-11 w-full min-w-0 rounded-lg border border-input bg-background px-2 text-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
              value={selected}
              disabled={render.isPending || loadingStyles}
              aria-invalid={unavailable || undefined}
              aria-describedby={unavailable || style?.description ? hintId : undefined}
              onChange={(event) => {
                setChoice(event.target.value);
                render.reset();
              }}
            >
              <option value="">Workspace default</option>
              {selected && !style && <option value={selected} disabled={unavailable}>{t("resumeVersions.savedStyle")}</option>}
              {templates.data?.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}
            </select>
            {unavailable ? (
              <p id={hintId} role="alert" className="text-sm text-destructive">That style is no longer available. Choose another.</p>
            ) : style?.description && (
              <p id={hintId} className="text-sm text-muted-foreground">{style.description}</p>
            )}
            {loadingStyles && <p role="status" className="text-sm text-muted-foreground">Loading styles…</p>}
            {templates.isError && (
              <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground" role="status">
                <span>Could not load styles.</span>
                <Button type="button" size="sm" variant="outline" onClick={() => void templates.refetch()}>{t("common.retry")}</Button>
              </div>
            )}
          </div>
          {render.isError && !unavailable && (
            <p role="alert" className="text-sm text-destructive">
              {errorCode === "resume_page_overflow"
                ? "This resume exceeds the page limit. Try a different style, shorten the content, or change the page limit in Rendering settings."
                : errorCode === "template_not_found"
                  ? "That style is no longer available. Choose another."
                  : errorCode === "NOT_FOUND"
                    ? "This version is no longer available."
                    : "Could not render the PDF. Try again or choose another style."}
            </p>
          )}
          <DialogFooter>
            <Button type="button" variant="outline" className="min-h-11" disabled={render.isPending} onClick={() => setOpen(false)}>{t("common.cancel")}</Button>
            <Button type="submit" className="h-auto min-h-11 max-w-full whitespace-normal py-2" disabled={!canSubmit}>
              {render.isPending && <Spinner data-icon="inline-start" aria-hidden="true" />}
              {render.isPending ? "Rendering PDF…" : pdfAvailable ? "Replace PDF" : "Render PDF"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
