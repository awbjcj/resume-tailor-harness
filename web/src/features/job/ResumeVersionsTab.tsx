import { useMemo, useRef } from "react";
import { RotateCcw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useRenderTemplates } from "@/features/settings/use-render-templates";
import type { components } from "@/lib/api/schema";
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
  const deleteVersions = (ids: number[]) => remove.mutate(ids, {
    onSuccess: () => {
      selection.clear();
      listRef.current?.focus();
    },
  });

  return (
    <>
      {onGenerate && (
        <div className={`mt-3 flex flex-wrap items-center gap-3 ${versions.length ? "justify-end" : "justify-between rounded-xl border border-dashed bg-background/60 p-4"}`}>
          {versions.length === 0 && <p className="text-sm text-muted-foreground">No saved resumes for this job.</p>}
          <Button size="sm" variant={versions.length ? "outline" : "default"} onClick={onGenerate}>
            <RotateCcw data-icon="inline-start" aria-hidden="true" />
            {versions.length ? "Generate again" : "Generate resume"}
          </Button>
        </div>
      )}
      {deletableIds.length > 0 && (
        <ArtifactSelectionBar
          kind="version"
          selectedCount={selection.selectedIds.length}
          allSelected={selection.allSelected}
          onToggleAll={selection.toggleAll}
          disabled={remove.isPending}
          onDelete={() => deleteVersions(selection.selectedIds)}
        />
      )}
      <ul ref={listRef} tabIndex={-1} aria-label="Saved resume versions" className="mt-4 space-y-3 rounded-xl focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">
        {newestFirst.map((version) => {
          const templateId = version.pdfTemplateId;
          const title = templates.data?.find((item) => item.id === templateId)?.title;
          return (
            <VersionRow
              key={version.id}
              jobId={jobId}
              version={version}
              appliedVersionId={appliedVersionId}
              templateTitle={title ?? templateId?.replace(/^custom:/, "")}
              selected={selection.isSelected(version.id)}
              onToggleSelected={selection.toggle}
              onDelete={(id) => deleteVersions([id])}
              deleting={remove.isPending}
            />
          );
        })}
        <RevisionRunPlaceholders jobId={jobId} kind="revise" label="Resume revision" />
      </ul>
    </>
  );
}
