import { useId, useState } from "react";
import { CheckCircle2, Download, Eye } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { openDownload } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { formatUserDateTime } from "@/lib/date-time";
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
    <li aria-labelledby={headingId} className={`min-w-0 rounded-xl border bg-background/70 p-3 sm:p-4 ${revision.justCreated ? "ring-2 ring-primary/40" : ""}`}>
      <div className="flex min-w-0 items-start gap-3">
        {onToggleSelected && (
          <Checkbox
            className="mt-1"
            checked={selected}
            disabled={applied || revision.active || selectBusy}
            onCheckedChange={() => onToggleSelected(version.id)}
            aria-label={t("resumeVersions.selectForDeletion", { id: version.id })}
          />
        )}
        <div className="min-w-0 flex-1 space-y-2">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
            <h3 id={headingId} className="font-heading text-base font-semibold tabular-nums">{t("resumeVersions.version", { id: version.id })}</h3>
            {applied && <Badge>Selected for application</Badge>}
            {revision.justCreated && <Badge variant="secondary">Just created</Badge>}
          </div>
          <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
            <span>{version.origin === "revision" ? "Revision" : version.origin === "external" ? "External draft" : t("resumeVersions.round", { round: version.round })}</span>
            {version.parentVersionId != null && <span>{t("resumeVersions.parent", { id: version.parentVersionId })}</span>}
            <time dateTime={version.createdAt}>{formatUserDateTime(version.createdAt, i18n.resolvedLanguage, { dateStyle: "medium", timeStyle: "short" })}</time>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            <Badge variant={eligible ? "outline" : "destructive"}>{eligible ? "Fact-lock passed" : failedGateLabel(version.failedGates)}</Badge>
            <span>Score {version.reviewScore ?? "not scored"}</span>
            {pdfAvailable && <Badge variant="secondary">PDF ready</Badge>}
            {pdfAvailable && templateTitle && <span className="min-w-0 [overflow-wrap:anywhere]">{templateTitle}</span>}
          </div>
          {version.instruction && <p className="[overflow-wrap:anywhere] text-sm text-muted-foreground">{version.instruction}</p>}
          {!eligible && (
            <p className="text-sm text-destructive">
              {applied
                ? "This resume failed fact-lock. Choose another resume or clear your selection before applying."
                : "This resume must pass fact-lock before you can select it for an application."}
            </p>
          )}
          {applied && eligible && <p className="text-sm text-muted-foreground">Selecting a document does not submit an application.</p>}
          {eligible && !pdfAvailable && <p className="text-sm text-muted-foreground">No PDF is available. Generate one for this version before uploading.</p>}
        </div>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2 border-t pt-3">
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
      <PdfPreviewDialog
        open={previewOpen}
        onOpenChange={setPreviewOpen}
        title={t("resumeVersions.previewTitle", { id: version.id })}
        previewPath={`/api/resume-versions/${version.id}/preview`}
        downloadPath={pdfPath}
      />
      <div className="mt-3">
        <ResumeRevisionEditor jobId={jobId} versionId={version.id} revision={revision} disabled={deleting} />
        <EvidencePortfolioDisclosure versionId={version.id} available={version.hasEvidencePortfolio} />
      </div>
    </li>
  );
}
