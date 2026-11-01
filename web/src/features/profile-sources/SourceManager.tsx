import { useRef, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Clock3,
  Download,
  FileText,
  FileUp,
  GitBranch,
  FolderGit2,
  RefreshCw,
  Star,
  Trash2,
  Undo2,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import {
  localizeSourceFragmentStatus,
  localizeSourceMode,
} from "@/i18n/dynamic-labels";
import { MaterialIntakeDialogs } from "./MaterialIntakeDialogs";
import {
  useDeleteSource,
  useDownloadSource,
  useGithubExclusions,
  usePatchSource,
  useReplaceSource,
  useRestoreGithubSources,
  useSkeleton,
  useSources,
  useUploadSources,
  type ProfileSource,
  type SkeletonEntry,
} from "./use-sources";

const MODES = ["literal", "synthesis"] as const;
const UPLOAD_MODES = ["auto", ...MODES, "project"] as const;
const selectClass =
  "h-11 w-full min-w-0 rounded-lg border border-input bg-background px-3 text-sm text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring [color-scheme:light] dark:[color-scheme:dark]";
const optionClass = "bg-popover text-popover-foreground";
const accepts = ".pdf,.docx,.txt,.md,.pptx,.xlsx,.html";

export function SourceManager({ disabled = false }: { disabled?: boolean }) {
  const { i18n } = useTranslation();
  const { data: sources, isLoading, isError, refetch } = useSources();
  const { data: skeleton } = useSkeleton();
  const upload = useUploadSources();
  const patch = usePatchSource();
  const remove = useDeleteSource();
  const replace = useReplaceSource();
  const download = useDownloadSource();
  const { data: exclusions = [] } = useGithubExclusions();
  const restore = useRestoreGithubSources();
  const fileInput = useRef<HTMLInputElement>(null);
  const replaceInput = useRef<HTMLInputElement>(null);
  const [uploadMode, setUploadMode] =
    useState<(typeof UPLOAD_MODES)[number]>("auto");
  const [uploadAnchor, setUploadAnchor] = useState("");
  const [replaceTargetId, setReplaceTargetId] = useState<string | null>(null);
  const [removeTarget, setRemoveTarget] = useState<ProfileSource | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadErrors, setUploadErrors] = useState<[string, string][]>([]);
  const busy =
    disabled ||
    uploading ||
    replace.isPending ||
    remove.isPending ||
    patch.isPending ||
    restore.isPending;
  const uploadFiles = async (files: File[]) => {
    if (!files.length || busy) return;
    setUploading(true);
    setUploadErrors([]);
    try {
      const result = await upload.uploadAll(
        files,
        uploadMode === "auto" ? undefined : uploadMode,
        uploadMode === "synthesis" ? uploadAnchor || null : null,
      );
      setUploadErrors(result?.failed ?? []);
    } finally {
      setUploading(false);
    }
  };
  if (isError)
    return (
      <div
        role="alert"
        className="space-y-3 rounded-xl border border-destructive/30 p-4"
      >
        <p>
          Source documents could not be loaded. Try again to manage your
          evidence.
        </p>
        <Button variant="outline" onClick={() => void refetch()}>
          Try again
        </Button>
      </div>
    );
  if (isLoading || !sources) return <Skeleton className="h-48 w-full" />;
  const ready = sources.filter(
    (source) =>
      source.fileExists !== false && source.fragmentStatus === "cached",
  ).length;
  return (
    <section
      aria-label="Source documents"
      className="min-w-0 rounded-xl border border-border bg-card [&_button]:h-auto [&_button]:min-h-10 [&_button]:max-w-full [&_button]:whitespace-normal"
    >
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-border p-4 sm:p-5">
        <div className="min-w-0 space-y-1">
          <h2 className="text-lg font-semibold">Source documents</h2>
          <p className="max-w-prose text-sm text-muted-foreground">
            Your resume provides your career history. Project dossiers add
            evidence from your work.
          </p>
          <p className="text-sm text-muted-foreground">{`${ready} of ${sources.length} sources ready`}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <MaterialIntakeDialogs disabled={busy} />
          <Button
            variant="outline"
            disabled={busy}
            onClick={() => fileInput.current?.click()}
          >
            {uploading ? (
              <Spinner data-icon="inline-start" />
            ) : (
              <FileUp data-icon="inline-start" aria-hidden="true" />
            )}
            {uploading ? "Uploading…" : "Add source"}
          </Button>
        </div>
      </div>
      <input
        ref={fileInput}
        type="file"
        multiple
        className="hidden"
        accept={accepts}
        onChange={(event) => {
          void uploadFiles(Array.from(event.target.files ?? []));
          event.target.value = "";
        }}
      />
      <input
        ref={replaceInput}
        type="file"
        className="hidden"
        accept={accepts}
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file && replaceTargetId && !busy)
            replace.mutate({ oldId: replaceTargetId, file });
          event.target.value = "";
          setReplaceTargetId(null);
        }}
      />
      <div
        className="border-b border-dashed border-border bg-muted/20 px-4 py-4 sm:px-5"
        onDragOver={(event) => event.preventDefault()}
        onDrop={(event) => {
          event.preventDefault();
          void uploadFiles(Array.from(event.dataTransfer.files));
        }}
      >
        <p className="text-sm">
          Drop files here or select Add source. You can upload PDFs, Word files,
          Markdown, and other supporting documents.
        </p>
        <div className="mt-3 grid grid-cols-[repeat(auto-fit,minmax(min(100%,16rem),1fr))] gap-3">
          <label className="space-y-1.5 text-sm font-medium">
            <span>Document type</span>
            <select
              aria-label="New source mode"
              className={selectClass}
              value={uploadMode}
              disabled={busy}
              onChange={(event) => {
                setUploadMode(event.target.value as typeof uploadMode);
                setUploadAnchor("");
              }}
            >
              {UPLOAD_MODES.map((mode) => (
                <option className={optionClass} key={mode} value={mode}>
                  {localizeSourceMode(mode, i18n.resolvedLanguage)}
                </option>
              ))}
            </select>
          </label>
          {uploadMode === "synthesis" ? (
            <label className="space-y-1.5 text-sm font-medium">
              <span>Attach evidence to</span>
              <select
                aria-label="New source anchor"
                className={selectClass}
                disabled={busy}
                value={uploadAnchor}
                onChange={(event) => setUploadAnchor(event.target.value)}
              >
                <option className={optionClass} value="">
                  Auto-anchor
                </option>
                {(skeleton ?? []).map((entry) => (
                  <option
                    className={optionClass}
                    key={entry.id}
                    value={entry.id}
                  >
                    {entry.label}
                  </option>
                ))}
              </select>
            </label>
          ) : (
            <p className="self-end text-sm text-muted-foreground">
              Auto-detect chooses a type based on file format and repository
              metadata. Change it if needed.
            </p>
          )}
        </div>
      </div>
      {uploadErrors.length ? (
        <div
          role="alert"
          className="space-y-1 border-b border-border p-4 text-sm text-destructive"
        >
          <p className="font-medium">
            Some files could not be added. Check the files and upload them
            again.
          </p>
          <ul>
            {uploadErrors.map(([name, error]) => (
              <li key={name} className="[overflow-wrap:anywhere]">
                {name}: {error}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {!sources.some((source) => source.primary) ? (
        <p className="border-b border-border p-4 text-sm text-muted-foreground">
          Add a resume to build your profile. Your other sources stay saved.
        </p>
      ) : ready < sources.length ? (
        <p className="border-b border-border p-4 text-sm text-muted-foreground">
          Sources are saved. Build your profile to use new or updated evidence.
        </p>
      ) : null}
      {sources.length === 0 ? (
        <div className="flex flex-col items-center gap-3 px-4 py-10 text-center">
          <FileText
            className="size-8 text-muted-foreground"
            aria-hidden="true"
          />
          <p className="font-medium">Start with your resume</p>
          <p className="max-w-sm text-sm text-muted-foreground">
            Add a resume, then connect GitHub or upload project dossiers to
            enrich your profile.
          </p>
        </div>
      ) : (
        <ul className="divide-y divide-border">
          {sources.map((source) => (
            <SourceCard
              key={source.id}
              source={source}
              skeleton={skeleton ?? []}
              language={i18n.resolvedLanguage}
              busy={busy}
              downloading={download.isPending}
              replacing={
                replace.isPending && replace.variables?.oldId === source.id
              }
              onDownload={() => download.mutate(source)}
              onReplace={() => {
                setReplaceTargetId(source.id);
                replaceInput.current?.click();
              }}
              onRemove={() => setRemoveTarget(source)}
              onPatch={patch.mutate}
            />
          ))}
        </ul>
      )}
      {exclusions.length ? (
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border bg-muted/20 p-4 sm:p-5">
          <p className="text-sm text-muted-foreground">
            Removed GitHub sources stay excluded from future syncs.
          </p>
          <Button
            variant="outline"
            className="h-auto min-h-11 max-w-full whitespace-normal text-left"
            disabled={busy}
            onClick={() => restore.mutate()}
          >
            <Undo2 data-icon="inline-start" aria-hidden="true" />
            Restore removed GitHub sources
          </Button>
        </div>
      ) : null}
      <Dialog
        open={removeTarget !== null}
        onOpenChange={(open) => {
          if (!open && !remove.isPending) setRemoveTarget(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Remove this source?</DialogTitle>
            <DialogDescription>
              The saved file and its extracted evidence will be removed. Rebuild
              your profile afterward to update its facts.
            </DialogDescription>
          </DialogHeader>
          <p className="text-sm font-medium [overflow-wrap:anywhere]">
            {removeTarget?.filename}
          </p>
          {removeTarget?.repoUrl || removeTarget?.origin === "github" ? (
            <p className="text-sm text-muted-foreground">
              This GitHub source will stay excluded from future syncs until you
              restore it.
            </p>
          ) : null}
          <DialogFooter>
            <Button
              variant="outline"
              disabled={remove.isPending}
              onClick={() => setRemoveTarget(null)}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={remove.isPending}
              onClick={() => {
                if (removeTarget)
                  remove.mutate(removeTarget.id, {
                    onSuccess: () => setRemoveTarget(null),
                  });
              }}
            >
              {remove.isPending ? <Spinner data-icon="inline-start" /> : null}
              Remove source
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
}

function SourceCard({
  source,
  skeleton,
  busy,
  downloading,
  replacing,
  language,
  onDownload,
  onReplace,
  onRemove,
  onPatch,
}: {
  source: ProfileSource;
  skeleton: SkeletonEntry[];
  busy: boolean;
  downloading: boolean;
  replacing: boolean;
  language: string | undefined;
  onDownload: () => void;
  onReplace: () => void;
  onRemove: () => void;
  onPatch: (patch: {
    id: string;
    mode?: "literal" | "synthesis";
    anchor?: string | null;
    primary?: boolean;
  }) => void;
}) {
  const missing = source.fileExists === false;
  const cached = !missing && source.fragmentStatus === "cached";
  const Icon = missing ? AlertCircle : cached ? CheckCircle2 : Clock3;
  return (
    <li>
      <article
        aria-label={source.filename}
        className="grid min-w-0 gap-4 p-4 sm:p-5"
      >
        <div className="flex min-w-0 items-start gap-3">
          <div
            className="hidden size-10 shrink-0 items-center justify-center sm:flex rounded-lg bg-muted text-muted-foreground"
            aria-hidden="true"
          >
            {source.mode === "project" ? (
              <FolderGit2 className="size-5" />
            ) : (
              <FileText className="size-5" />
            )}
          </div>
          <div className="min-w-0 flex-1 space-y-2">
            <h3 className="font-medium [overflow-wrap:anywhere]">
              {source.filename}
            </h3>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="outline">
                {source.primary
                  ? "Primary resume"
                  : source.mode === "project"
                    ? "Project dossier"
                    : "Supporting document"}
              </Badge>
              {source.origin === "github" ? (
                <Badge variant="outline">GitHub</Badge>
              ) : source.repoUrl ? (
                <Badge variant="outline">Uploaded (overrides GitHub)</Badge>
              ) : null}
              <Badge variant={cached ? "secondary" : "outline"}>
                <Icon className="mr-1 size-3" aria-hidden="true" />
                {missing ? (
                  <span>File missing</span>
                ) : (
                  localizeSourceFragmentStatus(source.fragmentStatus, language)
                )}
              </Badge>
            </div>
            {source.repoUrl || source.githubBranch ? (
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
                {source.repoUrl ? (
                  <span className="min-w-0 [overflow-wrap:anywhere]">
                    {source.repoUrl.replace(
                      /^https?:\/\/(www\.)?github.com\//,
                      "",
                    )}
                  </span>
                ) : null}
                {source.githubBranch ? (
                  <span className="inline-flex min-w-0 items-center gap-1.5">
                    <GitBranch
                      className="size-3.5 shrink-0"
                      aria-hidden="true"
                    />
                    <span className="[overflow-wrap:anywhere]">
                      {source.githubBranch}
                    </span>
                  </span>
                ) : null}
              </div>
            ) : null}
            {missing ? (
              <p className="text-sm text-destructive">
                Replace this file to restore its evidence, or remove the source.
              </p>
            ) : null}
          </div>
        </div>
        {!source.primary && source.mode !== "project" ? (
          <div className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,16rem),1fr))] gap-3">
            <label className="space-y-1.5 text-sm">
              <span>Read this document as</span>
              <select
                aria-label={`mode for ${source.filename}`}
                className={selectClass}
                disabled={busy}
                value={source.mode}
                onChange={(event) =>
                  onPatch({
                    id: source.id,
                    mode: event.target.value as "literal" | "synthesis",
                  })
                }
              >
                {MODES.map((mode) => (
                  <option className={optionClass} key={mode} value={mode}>
                    {localizeSourceMode(mode, language)}
                  </option>
                ))}
              </select>
            </label>
            {source.mode === "synthesis" ? (
              <label className="space-y-1.5 text-sm">
                <span>Attach evidence to</span>
                <select
                  aria-label={`anchor for ${source.filename}`}
                  className={selectClass}
                  disabled={busy}
                  value={source.anchor ?? ""}
                  onChange={(event) =>
                    onPatch({
                      id: source.id,
                      anchor: event.target.value || null,
                    })
                  }
                >
                  <option className={optionClass} value="">
                    Auto-anchor
                  </option>
                  {(skeleton ?? []).map((entry) => (
                    <option
                      className={optionClass}
                      key={entry.id}
                      value={entry.id}
                    >
                      {entry.label}
                    </option>
                  ))}
                </select>
              </label>
            ) : null}
          </div>
        ) : null}
        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="outline"
            disabled={missing || downloading}
            aria-label={`Download ${source.filename}`}
            onClick={() => onDownload()}
          >
            <Download data-icon="inline-start" aria-hidden="true" />
            Download
          </Button>
          <Button
            variant="outline"
            disabled={busy}
            aria-label={`Replace ${source.filename}`}
            onClick={() => {
              onReplace();
            }}
          >
            {replacing ? (
              <Spinner data-icon="inline-start" />
            ) : (
              <RefreshCw data-icon="inline-start" aria-hidden="true" />
            )}
            Replace
          </Button>
          {!source.primary && source.mode === "literal" ? (
            <Button
              variant="ghost"
              disabled={busy}
              aria-label={`Make ${source.filename} primary`}
              onClick={() => onPatch({ id: source.id, primary: true })}
            >
              <Star data-icon="inline-start" aria-hidden="true" />
              Primary
            </Button>
          ) : null}
          <Button
            variant="ghost"
            className="text-destructive hover:bg-destructive/10 hover:text-destructive sm:ml-auto"
            disabled={busy}
            aria-label={`Remove ${source.filename}`}
            onClick={() => onRemove()}
          >
            <Trash2 data-icon="inline-start" aria-hidden="true" />
            Remove
          </Button>
        </div>
      </article>
    </li>
  );
}
