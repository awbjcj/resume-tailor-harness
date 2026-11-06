import { useId, useState } from "react";
import { CheckCircle2, Download, Eye } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { openDownload } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { formatUserDateTime } from "@/lib/date-time";
import { cn } from "@/lib/utils";
import { ArtifactDeleteButton } from "./ArtifactDeleteButton";
import { EvidencePortfolioDisclosure } from "./EvidencePortfolioDisclosure";
import { PdfPreviewDialog } from "./PdfPreviewDialog";
import { ResumeRenderDialog } from "./ResumeRenderDialog";
import { ResumeRevisionEditor } from "./ResumeRevisionEditor";
import { resumeRevisionLifecycle, useArtifactRunIndex } from "./artifact-runs";
import { useDeselectResume, useSelectResume } from "./use-job-mutations";

type ResumeVersion = components["schemas"]["ResumeVersionOut"];

/** The failed gates identify what blocked the round, including provenance-only failures. */
export function failedGateLabel(failedGates: readonly string[] | undefined) {
  if (!failedGates?.length) return "Fact-lock failed";
  return `Fact-lock failed: ${failedGates.join(", ")}`;
}

export function VersionRow({
  jobId,
  version,
  appliedVersionId,
  templateTitle,
  selected = false,
  deleting = false,
  onToggleSelected,
  onDelete,
}: {
  jobId: number;
  version: ResumeVersion;
  appliedVersionId: number | null;
  templateTitle?: string;
  selected?: boolean;
  deleting?: boolean;
  onToggleSelected?: (id: number) => void;
  onDelete?: (id: number) => void;
}) {
  const { t, i18n } = useTranslation();
  const headingId = useId();
  const [previewOpen, setPreviewOpen] = useState(false);
  const revision = resumeRevisionLifecycle(useArtifactRunIndex(), version.id);
  const select = useSelectResume(jobId);
  const deselect = useDeselectResume(jobId);
  const applied = appliedVersionId === version.id;
  const eligible = version.applicationEligible ?? (version.factCheckPassed && !version.failedGates?.length);
  const pdfAvailable = version.pdfAvailable ?? Boolean(version.pdfPath);
  const selectBusy = select.isPending || deselect.isPending || deleting;
  const pdfPath = `/api/resume-versions/${version.id}/pdf`;

  return (
    <li aria-labelledby={headingId} className={cn(
      "min-w-0 px-3 py-2.5 sm:px-4",
      revision.justCreated && "bg-primary/5 first:rounded-t-lg last:rounded-b-lg",
    )}>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <div className="flex min-w-0 flex-1 basis-64 items-start gap-2.5">
          {onToggleSelected && (
            <Checkbox
              className="mt-0.5"
              checked={selected}
              disabled={applied || revision.active || selectBusy}
              onCheckedChange={() => onToggleSelected(version.id)}
              aria-label={t("resumeVersions.selectForDeletion", { id: version.id })}
            />
          )}
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <h3 id={headingId} className="font-heading text-sm font-semibold tabular-nums">{t("resumeVersions.version", { id: version.id })}</h3>
              {applied && <Badge>Selected for application</Badge>}
              {revision.justCreated && <Badge variant="secondary">Just created</Badge>}
              <Badge variant={eligible ? "outline" : "destructive"} className="h-auto min-h-5 max-w-full wrap-anywhere whitespace-normal">
                {eligible ? "Fact-lock passed" : failedGateLabel(version.failedGates)}
              </Badge>
              {pdfAvailable && <Badge variant="secondary">PDF ready</Badge>}
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
              <span>{version.origin === "revision" ? "Revision" : version.origin === "external" ? "External draft" : t("resumeVersions.round", { round: version.round })}</span>
              {version.parentVersionId != null && <span>{t("resumeVersions.parent", { id: version.parentVersionId })}</span>}
              <time dateTime={version.createdAt}>{formatUserDateTime(version.createdAt, i18n.resolvedLanguage, { dateStyle: "medium", timeStyle: "short" })}</time>
              <span>Score {version.reviewScore ?? "not scored"}</span>
              {pdfAvailable && templateTitle && <span className="min-w-0 wrap-anywhere">{templateTitle}</span>}
            </div>
          </div>
        </div>
        <div className="flex min-w-0 max-w-full flex-wrap items-center gap-1.5">
          {pdfAvailable && (
            <>
              <Button size="sm" variant="outline" disabled={deleting} onClick={() => setPreviewOpen(true)}>
                <Eye data-icon="inline-start" aria-hidden="true" />
                Preview
              </Button>
              <a
                className={buttonVariants({ size: "sm", variant: "outline", className: "aria-disabled:opacity-50" })}
                href={pdfPath}
                aria-disabled={deleting || undefined}
                onClick={(event) => {
                  event.preventDefault();
                  if (!deleting) void openDownload(event.currentTarget.href);
                }}
              >
                <Download data-icon="inline-start" aria-hidden="true" />
                Download
              </a>
            </>
          )}
          <ResumeRenderDialog jobId={jobId} versionId={version.id} templateId={version.pdfTemplateId} pdfAvailable={pdfAvailable} applied={applied} disabled={deleting} />
          <Button
            size="sm"
            variant="outline"
            disabled={selectBusy || (!applied && !eligible)}
            onClick={() => applied ? deselect.mutate() : select.mutate(version.id)}
          >
            {!applied && <CheckCircle2 data-icon="inline-start" aria-hidden="true" />}
            {applied ? "Clear selection" : "Use for application"}
          </Button>
          {onDelete && (
            <ArtifactDeleteButton
              noun="version"
              label={t("resumeVersions.deleteTarget", { id: version.id })}
              showLabel
              applied={applied}
              disabled={revision.active || selectBusy}
              onConfirm={() => onDelete(version.id)}
            />
          )}
        </div>
      </div>
      <PdfPreviewDialog
        open={previewOpen}
        onOpenChange={setPreviewOpen}
        title={t("resumeVersions.previewTitle", { id: version.id })}
        previewPath={`/api/resume-versions/${version.id}/preview`}
        downloadPath={pdfPath}
      />
      <div className="mt-2 space-y-1 text-xs text-muted-foreground">
        {version.instruction && <p className="wrap-anywhere">{version.instruction}</p>}
        {!eligible && (
          <p className="text-destructive">
            {applied
              ? "This resume failed fact-lock. Choose another resume or clear your selection before applying."
              : "This resume must pass fact-lock before you can select it for an application."}
          </p>
        )}
        {applied && eligible && <p>Selecting a document does not submit an application.</p>}
        {eligible && !pdfAvailable && <p>No PDF is available. Generate one for this version before uploading.</p>}
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <ResumeRevisionEditor jobId={jobId} versionId={version.id} revision={revision} disabled={deleting} />
          <EvidencePortfolioDisclosure versionId={version.id} available={version.hasEvidencePortfolio} />
        </div>
      </div>
    </li>
  );
}
