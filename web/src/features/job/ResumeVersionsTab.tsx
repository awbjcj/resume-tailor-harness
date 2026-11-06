import { useMemo, useRef } from "react";
import { FilePlus2 } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { useRenderTemplates } from "@/features/settings/use-render-templates";
import type { components } from "@/lib/api/schema";
import { cn } from "@/lib/utils";
import { ArtifactSelectionBar } from "./ArtifactSelectionBar";
import { RevisionRunPlaceholders } from "./RevisionRunPlaceholders";
import { resumeRevisionLifecycle, useArtifactRunIndex } from "./artifact-runs";
import { useArtifactSelection } from "./use-artifact-selection";
import { useDeleteVersions } from "./use-job-mutations";
import { VersionRow } from "./VersionRow";

type ResumeVersion = components["schemas"]["ResumeVersionOut"];

export function ResumeVersionsTab({
  jobId,
  versions,
  appliedVersionId,
  onGenerate,
}: {
  jobId: number;
  versions: ResumeVersion[];
  appliedVersionId: number | null;
  onGenerate?: () => void;
}) {
  const { t } = useTranslation();
  const runIndex = useArtifactRunIndex();
  const deletableIds = useMemo(
    () => versions.map((v) => v.id).filter((id) => id !== appliedVersionId && !resumeRevisionLifecycle(runIndex, id).active),
    [versions, appliedVersionId, runIndex],
  );
  const selection = useArtifactSelection(deletableIds);
  const remove = useDeleteVersions(jobId);
  const listRef = useRef<HTMLUListElement>(null);
  const templates = useRenderTemplates(versions.some((v) => Boolean(v.pdfTemplateId)));
  const newestFirst = useMemo(() => [...versions].sort((a, b) => b.id - a.id), [versions]);
  const hasVersions = versions.length > 0;
  const deleteVersions = (ids: number[]) => remove.mutate(ids, {
    onSuccess: () => {
      selection.clear();
      listRef.current?.focus();
    },
  });

  return (
    <div className="space-y-3">
      {(onGenerate || deletableIds.length > 0) && (
        <div className={cn(
          "flex flex-wrap items-center gap-2",
          !hasVersions && "rounded-lg border border-dashed bg-background/60 px-3 py-2",
        )}>
          {!hasVersions && <p className="text-sm text-muted-foreground">No resume versions yet.</p>}
          {deletableIds.length > 0 && (
            <ArtifactSelectionBar
              className="mt-0 border-0 bg-transparent p-0"
              kind="version"
              selectedCount={selection.selectedIds.length}
              allSelected={selection.allSelected}
              onToggleAll={selection.toggleAll}
              disabled={remove.isPending}
              onDelete={() => deleteVersions(selection.selectedIds)}
            />
          )}
          {onGenerate && (
            <Button className="ml-auto" size="sm" variant={hasVersions ? "outline" : "default"} onClick={onGenerate}>
              <FilePlus2 data-icon="inline-start" aria-hidden="true" />
              {hasVersions ? "Generate a new version" : "Generate resume"}
            </Button>
          )}
        </div>
      )}
      <ul ref={listRef} tabIndex={-1} aria-label="Resume versions"
        className="divide-y rounded-lg border bg-background/70 empty:border-0 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">
        {newestFirst.map((version) => {
          const templateId = version.pdfTemplateId;
          const title = templates.data?.find((item) => item.id === templateId)?.title;
          const customName = templateId?.startsWith("custom:") ? templateId.slice("custom:".length) : undefined;
          return (
            <VersionRow
              key={version.id}
              jobId={jobId}
              version={version}
              appliedVersionId={appliedVersionId}
              templateTitle={title ?? customName ?? (templateId ? t("resumeVersions.savedStyle") : undefined)}
              selected={selection.isSelected(version.id)}
              onToggleSelected={selection.toggle}
              onDelete={(id) => deleteVersions([id])}
              deleting={remove.isPending}
            />
          );
        })}
        <RevisionRunPlaceholders jobId={jobId} kind="revise" label="Resume revision"
          className="rounded-none border-0 px-3 py-2.5 first:rounded-t-lg last:rounded-b-lg sm:px-4" />
      </ul>
    </div>
  );
}
