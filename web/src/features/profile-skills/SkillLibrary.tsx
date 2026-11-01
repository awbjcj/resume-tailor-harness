import { useSkillCopy } from "@/i18n/skill-copy";
import { useState } from "react";
import { useIsMutating } from "@tanstack/react-query";
import {
  Check,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  FolderCog,
  LayoutGrid,
  List,
  GitMerge,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  Sparkles,
  Trash2,
  Undo2,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
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
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { Switch } from "@/components/ui/switch";
import { useActiveRun } from "@/features/runs/use-active-run";
import { useLaunchRun } from "@/features/runs/use-launch-run";
import {
  useMatrix,
  useDeleteSkill,
  useRestoreSkill,
  useSuppressedSkills,
} from "@/features/settings/use-matrix";
import { localizeRunError, localizeRunPhase } from "@/i18n/dynamic-labels";
import { api, unwrap } from "@/lib/api/client";
import {
  localizeSkillContainer,
  localizeSkillLabel,
} from "@/i18n/skill-labels";
import {
  LibrarySelect,
  SkillEditorDialog,
  type LibraryRow,
} from "./SkillEditorDialog";
import { SkillCompactView } from "./SkillCompactView";
import { SkillContextPopover } from "./SkillContextPopover";
import { SkillOrganizationDialog } from "./SkillOrganizationDialog";
import {
  SKILL_MUTATION_KEY,
  useCleanProfileSkills,
  useMergeProfileSkills,
  useSkillCleanup,
  useSkillCleanupPolicy,
} from "./use-profile-skills";

const PAGE_SIZE = 40;
const ACTIVE = ["queued", "running", "cancelling"];

function CleanupDialog({ onClose }: { onClose: () => void }) {
  const copy = useSkillCopy();
  const { i18n } = useTranslation();
  const preview = useSkillCleanup(true);
  const clean = useCleanProfileSkills();
  const changes =
    (preview.data?.merges.length ?? 0) + (preview.data?.pruned.length ?? 0);
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !clean.isPending) onClose();
      }}
    >
      <DialogContent
        overlayClassName="transition-none"
        className="transition-none sm:max-w-lg"
        showCloseButton={!clean.isPending}
      >
        <DialogHeader>
          <DialogTitle>{copy.clean_up_profile_skills}</DialogTitle>
          <DialogDescription>{copy.cleanupDescription}</DialogDescription>
        </DialogHeader>
        {preview.isPending ? (
          <Skeleton className="h-24" aria-label={copy.checking_skills} />
        ) : preview.isError ? (
          <div role="alert">
            <p>{preview.error.message}</p>
            <Button variant="outline" onClick={() => void preview.refetch()}>
              Try again
            </Button>
          </div>
        ) : (
          <div className="max-h-[50svh] space-y-4 overflow-y-auto">
            {changes === 0 ? (
              <p className="flex items-center gap-2 py-3 text-sm">
                <Check className="size-4 text-primary" aria-hidden />
                {copy.your_skill_library_is_already_clean}
              </p>
            ) : (
              <>
                <p className="text-sm text-muted-foreground">
                  {`${preview.data.beforeCount} skills → ${preview.data.afterCount} skills`}
                </p>
                {preview.data.merges.length > 0 ? (
                  <section>
                    <h3 className="mb-2 text-sm font-semibold">
                      {copy.merge_duplicates}
                    </h3>
                    <ul className="space-y-2">
                      {preview.data.merges.map((merge, i) => (
                        <li key={i} className="break-words text-sm">
                          <span className="font-medium">{merge.into}</span>
                          <p className="text-muted-foreground">
                            {merge.names.join(", ")}
                          </p>
                        </li>
                      ))}
                    </ul>
                  </section>
                ) : null}
                {preview.data.pruned.length > 0 ? (
                  <section>
                    <h3 className="mb-2 text-sm font-semibold">
                      {copy.remove_non_skills}
                    </h3>
                    <ul className="space-y-2">
                      {preview.data.pruned.map((skill) => (
                        <li key={skill.token} className="break-words text-sm">
                          <span className="font-medium">{skill.display}</span>
                          <p className="text-muted-foreground">
                            {localizeSkillLabel(
                              skill.reason,
                              i18n.resolvedLanguage,
                            )}
                          </p>
                        </li>
                      ))}
                    </ul>
                  </section>
                ) : null}
                <p className="text-xs text-muted-foreground">
                  {copy.cleanupRestore}
                </p>
              </>
            )}
          </div>
        )}
        <DialogFooter>
          <Button
            variant="outline"
            onClick={onClose}
            disabled={clean.isPending}
          >
            Close
          </Button>
          <Button
            disabled={!changes || preview.isFetching || clean.isPending}
            onClick={() => clean.mutate(undefined, { onSuccess: onClose })}
          >
            {clean.isPending ? (
              <Spinner aria-hidden />
            ) : (
              <Sparkles aria-hidden />
            )}
            {clean.isPending ? copy.cleaning_placeholder : copy.apply_cleanup}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function MergeDialog({
  rows,
  onClose,
}: {
  rows: LibraryRow[];
  onClose: () => void;
}) {
  const copy = useSkillCopy();
  const [into, setInto] = useState(rows[0]?.key ?? "");
  const merge = useMergeProfileSkills();
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !merge.isPending) onClose();
      }}
    >
      <DialogContent
        overlayClassName="transition-none"
        className="transition-none sm:max-w-lg"
        showCloseButton={!merge.isPending}
      >
        <DialogHeader>
          <DialogTitle>{copy.merge_selected_skills}</DialogTitle>
          <DialogDescription>{copy.mergeDescription}</DialogDescription>
        </DialogHeader>
        <div className="grid min-w-0 gap-2">
          <label htmlFor="merge-skill-name" className="text-sm font-medium">
            {copy.keep_this_skill}
          </label>
          <LibrarySelect
            id="merge-skill-name"
            value={into}
            onChange={setInto}
            disabled={merge.isPending}
          >
            {rows.map((row) => (
              <option key={row.key} value={row.key}>
                {row.display}
              </option>
            ))}
          </LibrarySelect>
        </div>
        <p className="break-words text-sm text-muted-foreground">
          {rows.map((row) => row.display).join(", ")}
        </p>
        {merge.error ? (
          <p role="alert" className="text-sm text-destructive">
            {merge.error.message}
          </p>
        ) : null}
        <DialogFooter>
          <Button
            variant="outline"
            onClick={onClose}
            disabled={merge.isPending}
          >
            Cancel
          </Button>
          <Button
            disabled={merge.isPending || rows.length < 2}
            onClick={() =>
              merge.mutate(
                { keys: rows.map((r) => r.key), into },
                { onSuccess: onClose },
              )
            }
          >
            <GitMerge aria-hidden />
            {merge.isPending ? copy.merging_placeholder : copy.merge_skills}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function SkillLibrary({ disabled = false }: { disabled?: boolean }) {
  const copy = useSkillCopy();
  const matrix = useMatrix();
  const suppressed = useSuppressedSkills();
  const remove = useDeleteSkill();
  const restore = useRestoreSkill();
  const cleanup = useSkillCleanup(!!matrix.data?.generatedAt);
  const policy = useSkillCleanupPolicy();
  const mutating = useIsMutating({ mutationKey: SKILL_MUTATION_KEY });
  const { launch } = useLaunchRun();
  const { i18n } = useTranslation();
  const run = useActiveRun("profile-skills-rebuild");
  const profileRun = useActiveRun("profile-build");
  const [launching, setLaunching] = useState(false);
  const rebuilding = launching || !!(run && ACTIVE.includes(run.status));
  const busy =
    disabled ||
    rebuilding ||
    !!(profileRun && ACTIVE.includes(profileRun.status)) ||
    mutating > 0;
  const [search, setSearch] = useState("");
  const [categoryFilter, setCategory] = useState("all");
  const [groupFilter, setGroup] = useState("all");
  const [origin, setOrigin] = useState("all");
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [editor, setEditor] = useState<LibraryRow | "new" | null>(null);
  const [newSkillGroup, setNewSkillGroup] = useState<string>();
  const [editorFocus, setEditorFocus] = useState<HTMLElement | null>(null);
  const [view, setView] = useState<"list" | "compact">(() => {
    try {
      return localStorage.getItem("profile-skills-view") === "compact"
        ? "compact"
        : "list";
    } catch {
      return "list";
    }
  });
  const [organizing, setOrganizing] = useState(false);
  const [cleaning, setCleaning] = useState(false);
  const [merging, setMerging] = useState(false);

  if (matrix.isPending)
    return (
      <Skeleton
        className="h-64 w-full"
        aria-label={copy.loading_skill_matrix}
      />
    );
  if (matrix.isError)
    return (
      <Alert variant="destructive">
        <CircleAlert aria-hidden />
        <AlertTitle>{copy.couldn_t_load_the_skill_matrix}</AlertTitle>
        <AlertDescription>
          {matrix.error.message}
          <Button variant="outline" onClick={() => void matrix.refetch()}>
            Try again
          </Button>
        </AlertDescription>
      </Alert>
    );

  const rows = matrix.data.rows ?? [];
  const groups = (matrix.data.groups ?? []).map((item) =>
    localizeSkillContainer(item, i18n.resolvedLanguage),
  );
  const categories = matrix.data.categories?.length
    ? matrix.data.categories.map((item) =>
        localizeSkillContainer(item, i18n.resolvedLanguage),
      )
    : [{ slug: "other", label: "Other", customized: false }];
  const category = categories.some((item) => item.slug === categoryFilter)
    ? categoryFilter
    : "all";
  const group = groups.some(
    (item) =>
      item.slug === groupFilter &&
      (category === "all" || item.category === category),
  )
    ? groupFilter
    : "all";
  const byGroup = new Map(groups.map((g) => [g.slug, g]));
  const rowCategory = (row: LibraryRow) =>
    byGroup.get(row.group ?? "other")?.category ?? "other";
  const normalized = search.trim().toLocaleLowerCase();
  const filtered = rows.filter(
    (row) =>
      (category === "all" || rowCategory(row) === category) &&
      (group === "all" || (row.group ?? "other") === group) &&
      (origin === "all" || row.inferred === (origin === "inferred")) &&
      [row.display, ...(row.aliases ?? [])].some((name) =>
        name.toLocaleLowerCase().includes(normalized),
      ),
  );
  const safePage = Math.min(
    page,
    Math.max(0, Math.ceil(filtered.length / PAGE_SIZE) - 1),
  );
  const visible = filtered.slice(
    safePage * PAGE_SIZE,
    (safePage + 1) * PAGE_SIZE,
  );
  const selectedRows = rows.filter((row) => selected.has(row.key));
  const built = !!matrix.data.generatedAt;
  const unclassified =
    run?.result && "unclassified" in run.result ? run.result.unclassified : 0;
  const chooseCategory = (slug: string) => {
    setCategory(slug);
    setGroup("all");
    setPage(0);
  };
  function openEditor(row: LibraryRow, trigger: HTMLElement | null) {
    setEditorFocus(trigger);
    setEditor(row);
  }
  function addToGroup(slug: string, trigger: HTMLElement | null = null) {
    setNewSkillGroup(slug);
    setEditorFocus(trigger);
    setEditor("new");
  }
  function toggleSelection(key: string) {
    setSelected((previous) => {
      const next = new Set(previous);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }
  function chooseView(next: "list" | "compact") {
    setView(next);
    try {
      localStorage.setItem("profile-skills-view", next);
    } catch {
      /* The view still works when storage is unavailable. */
    }
  }
  const filters = (
    <div className="flex min-w-0 flex-wrap gap-2">
      {view === "compact" ? (
        <LibrarySelect
          value={category}
          onChange={chooseCategory}
          label={copy.skill_categories}
        >
          <option value="all">{copy.all_skills}</option>
          {categories.map((item) => (
            <option key={item.slug} value={item.slug}>
              {item.label}
            </option>
          ))}
        </LibrarySelect>
      ) : null}
      <div className="relative min-w-0 flex-[1_1_15rem]">
        <Search
          aria-hidden
          className="pointer-events-none absolute left-3 top-3 size-4 text-muted-foreground"
        />
        <Input
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(0);
          }}
          aria-label={copy.search_skills_and_aliases}
          placeholder={copy.search_skills_and_aliases_placeholder}
          className="pl-9"
        />
      </div>
      <LibrarySelect
        value={group}
        onChange={(v) => {
          setGroup(v);
          setPage(0);
        }}
        label={copy.filter_by_group}
      >
        <option value="all">{copy.all_groups}</option>
        {groups
          .filter((g) => category === "all" || g.category === category)
          .map((g) => (
            <option key={g.slug} value={g.slug}>
              {g.label}
            </option>
          ))}
      </LibrarySelect>
      <LibrarySelect
        value={origin}
        onChange={(v) => {
          setOrigin(v);
          setPage(0);
        }}
        label={copy.filter_by_evidence}
      >
        <option value="all">{copy.all_evidence}</option>
        <option value="literal">{copy.listed_skills}</option>
        <option value="inferred">{copy.inferred_skills}</option>
      </LibrarySelect>
    </div>
  );
  const selectionBar =
    selectedRows.length > 0 ? (
      <div
        className="flex flex-wrap items-center gap-2 rounded-lg bg-muted px-3 py-2"
        role="status"
      >
        <span className="mr-auto text-sm">{selectedRows.length} selected</span>
        <Button
          variant="outline"
          size="sm"
          disabled={
            selectedRows.length < 2 || selectedRows.length > 100 || busy
          }
          onClick={() => setMerging(true)}
        >
          <GitMerge aria-hidden />
          {copy.merge_selected}
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setSelected(new Set())}
        >
          Clear selection
        </Button>
      </div>
    ) : null;
  function rebuild(reclassifyOnly: boolean) {
    if (busy || !built) return;
    setLaunching(true);
    void launch("profile-skills-rebuild", () =>
      unwrap(
        api.POST("/api/profile/skills/rebuild", { body: { reclassifyOnly } }),
      ),
    ).finally(() => setLaunching(false));
  }

  return (
    <section
      aria-labelledby="skill-library-heading"
      className="@container/library min-w-0 space-y-5 [overflow-wrap:anywhere] [&_[data-slot=button]]:h-auto [&_[data-slot=button]]:min-h-9 [&_[data-slot=button]]:max-w-full [&_[data-slot=button]]:whitespace-normal"
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 max-w-prose space-y-1">
          <h2
            id="skill-library-heading"
            className="text-xl font-semibold tracking-tight"
          >
            {copy.your_skill_library}
          </h2>
          <p className="text-sm leading-relaxed text-muted-foreground">
            {copy.libraryDescription}
          </p>
        </div>
        <div className="flex min-w-0 flex-wrap gap-2">
          <Button
            variant="outline"
            disabled={busy || !built}
            onClick={() => rebuild(false)}
          >
            {rebuilding ? <Spinner aria-hidden /> : <RefreshCw aria-hidden />}
            Rebuild skills
          </Button>
          <Button
            disabled={busy || !built}
            onClick={() => {
              setNewSkillGroup(undefined);
              setEditorFocus(null);
              setEditor("new");
            }}
          >
            <Plus aria-hidden />
            Add skill
          </Button>
        </div>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b pb-4 text-sm">
        <p className="text-muted-foreground">
          {`${rows.length} skills · ${groups.length} groups`}
        </p>
        <div
          role="group"
          aria-label={copy.viewLabel}
          className="inline-flex max-w-full flex-wrap rounded-lg border border-border p-0.5"
        >
          <Button
            size="sm"
            variant={view === "compact" ? "secondary" : "ghost"}
            aria-pressed={view === "compact"}
            className="transition-none"
            onClick={() => chooseView("compact")}
          >
            <LayoutGrid aria-hidden />
            {copy.compactView}
          </Button>
          <Button
            size="sm"
            variant={view === "list" ? "secondary" : "ghost"}
            aria-pressed={view === "list"}
            className="transition-none"
            onClick={() => chooseView("list")}
          >
            <List aria-hidden />
            {copy.detailedView}
          </Button>
        </div>
        <div className="flex flex-wrap gap-1">
          <Button
            variant="ghost"
            size="sm"
            disabled={busy || !built}
            onClick={() => rebuild(true)}
          >
            <Sparkles aria-hidden />
            {copy.reclassify}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            disabled={busy}
            onClick={() => setOrganizing(true)}
          >
            <FolderCog aria-hidden />
            {copy.groups_categories}
          </Button>
        </div>
      </div>
      {rebuilding ? (
        <p
          role="status"
          className="flex items-center gap-2 text-sm text-muted-foreground"
        >
          <Spinner />
          {localizeRunPhase(
            run?.phase ?? "Rebuilding profile skills",
            i18n.resolvedLanguage,
          )}
        </p>
      ) : run?.status === "failed" ? (
        <p role="alert" className="text-sm text-destructive">
          {localizeRunError(run.error, i18n.resolvedLanguage)}
        </p>
      ) : run?.status === "succeeded" ? (
        <p role="status" className="text-sm text-muted-foreground">
          {copy.rebuilt}
        </p>
      ) : null}
      {run?.status === "succeeded" &&
      typeof unclassified === "number" &&
      unclassified > 0 ? (
        <p role="status" className="text-sm text-muted-foreground">
          {copy.incomplete}
        </p>
      ) : null}
      {!built ? (
        <div className="py-12 text-center">
          <h3 className="font-semibold">{copy.start_with_your_profile}</h3>
          <p className="mx-auto mt-2 max-w-sm text-sm text-muted-foreground">
            {copy.firstProfile}
          </p>
        </div>
      ) : (
        <>
          {view === "compact" ? (
            <div className="min-w-0 space-y-4">
              {filters}
              {selectionBar}
              <SkillCompactView
                rows={filtered}
                allRows={rows}
                groups={groups}
                categories={categories}
                disabled={busy}
                category={category}
                group={group}
                hasSearch={!!search.trim() || origin !== "all"}
                selected={selected}
                onEdit={openEditor}
                onDelete={(key) => remove.mutate(key)}
                onAdd={addToGroup}
                onSelect={toggleSelection}
                onClear={() => {
                  setSearch("");
                  chooseCategory("all");
                  setOrigin("all");
                }}
              />
            </div>
          ) : (
            <div className="grid min-w-0 gap-5 @3xl/library:grid-cols-[12rem_minmax(0,1fr)]">
              <nav
                aria-label={copy.skill_categories}
                className="flex min-w-0 flex-wrap content-start gap-1 @3xl/library:flex-col"
              >
                {[{ slug: "all", label: copy.all_skills }, ...categories].map(
                  (item) => (
                    <Button
                      key={item.slug}
                      variant={category === item.slug ? "secondary" : "ghost"}
                      className="h-auto min-h-10 max-w-full justify-between gap-3 whitespace-normal text-left text-sm"
                      aria-pressed={category === item.slug}
                      onClick={() => chooseCategory(item.slug)}
                    >
                      <span>{item.label}</span>
                      <span className="tabular-nums text-muted-foreground">
                        {item.slug === "all"
                          ? rows.length
                          : rows.filter((row) => rowCategory(row) === item.slug)
                              .length}
                      </span>
                    </Button>
                  ),
                )}
              </nav>
              <div className="min-w-0 space-y-3">
                {filters}
                {selectionBar}
                <div className="@container/skills rounded-xl border border-border">
                  <div className="flex items-center gap-3 border-b bg-muted/30 px-4 py-2.5 text-xs text-muted-foreground">
                    <Checkbox
                      aria-label={copy.select_visible_skills}
                      disabled={busy || !visible.length}
                      checked={
                        visible.length > 0 &&
                        visible.every((row) => selected.has(row.key))
                      }
                      onCheckedChange={(checked) =>
                        setSelected((previous) => {
                          const next = new Set(previous);
                          visible.forEach((row) => {
                            if (checked) next.add(row.key);
                            else next.delete(row.key);
                          });
                          return next;
                        })
                      }
                    />
                    <span className="flex-1">{copy.skill_aliases}</span>
                    <span className="hidden w-44 @2xl/skills:block">
                      {copy.group}
                    </span>
                    <span className="w-20 text-right">Actions</span>
                  </div>
                  {visible.length === 0 ? (
                    <div className="px-5 py-12 text-center">
                      <p className="font-medium">
                        {rows.length
                          ? "No matching skills"
                          : copy.no_skills_yet}
                      </p>
                      <p className="mt-1 text-sm text-muted-foreground">
                        {rows.length ? copy.noMatches : copy.noSkills}
                      </p>
                      {rows.length ? (
                        <Button
                          variant="ghost"
                          className="mt-3"
                          onClick={() => {
                            setSearch("");
                            chooseCategory("all");
                            setOrigin("all");
                          }}
                        >
                          {copy.clear_filters}
                        </Button>
                      ) : null}
                    </div>
                  ) : (
                    <ul className="divide-y">
                      {visible.map((row) => (
                        <li
                          key={row.key}
                          className="flex min-w-0 items-start gap-3 px-4 py-3.5"
                        >
                          <Checkbox
                            className="mt-1.5"
                            aria-label={`Select ${row.display}`}
                            checked={selected.has(row.key)}
                            disabled={busy}
                            onCheckedChange={(checked) =>
                              setSelected((previous) => {
                                const next = new Set(previous);
                                if (checked) next.add(row.key);
                                else next.delete(row.key);
                                return next;
                              })
                            }
                          />
                          <div className="min-w-0 flex-1">
                            <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                              <SkillContextPopover
                                row={row}
                                groups={groups}
                                categories={categories}
                                disabled={busy}
                                selected={selected.has(row.key)}
                                onEdit={openEditor}
                                onDelete={(key) => remove.mutate(key)}
                                onSelect={toggleSelection}
                              />
                              {row.inferred ? (
                                <Badge
                                  variant="outline"
                                  className="text-[0.65rem]"
                                >
                                  {copy.inferred}
                                </Badge>
                              ) : null}
                            </div>
                            {row.aliases?.length ? (
                              <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-muted-foreground">
                                {row.aliases.join(", ")}
                              </p>
                            ) : null}
                            <p className="mt-1 text-xs text-muted-foreground">
                              {row.inferred
                                ? copy.linked_to_profile_evidence
                                : copy.listed_in_your_profile}
                              <span className="@2xl/skills:hidden">
                                {" "}
                                ·{" "}
                                {byGroup.get(row.group ?? "other")?.label ??
                                  "Other"}
                              </span>
                            </p>
                          </div>
                          <div className="hidden w-44 shrink-0 pt-1 @2xl/skills:block">
                            <span className="text-xs leading-relaxed text-muted-foreground">
                              {byGroup.get(row.group ?? "other")?.label ??
                                "Other"}
                            </span>
                            {row.groupSource === "correction" ? (
                              <p className="mt-1 text-[0.65rem] text-muted-foreground">
                                {copy.manually_assigned}
                              </p>
                            ) : null}
                          </div>
                          <div className="flex w-20 shrink-0 justify-end">
                            <Button
                              variant="ghost"
                              size="icon-sm"
                              aria-label={`Edit ${row.display}`}
                              disabled={busy}
                              onClick={(event) =>
                                openEditor(row, event.currentTarget)
                              }
                            >
                              <Pencil aria-hidden />
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon-sm"
                              aria-label={`Delete ${row.display}`}
                              className="text-destructive hover:bg-destructive/10 hover:text-destructive"
                              disabled={busy}
                              onClick={() => remove.mutate(row.key)}
                            >
                              <Trash2 aria-hidden />
                            </Button>
                          </div>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
                <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
                  <span aria-live="polite">
                    {`${filtered.length} matching skills`}
                  </span>
                  {filtered.length > PAGE_SIZE ? (
                    <div className="flex items-center gap-2">
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        aria-label={copy.previous_skills_page}
                        disabled={safePage === 0}
                        onClick={() => setPage(safePage - 1)}
                      >
                        <ChevronLeft aria-hidden />
                      </Button>
                      <span className="tabular-nums">
                        {safePage + 1} /{" "}
                        {Math.ceil(filtered.length / PAGE_SIZE)}
                      </span>
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        aria-label={copy.next_skills_page}
                        disabled={(safePage + 1) * PAGE_SIZE >= filtered.length}
                        onClick={() => setPage(safePage + 1)}
                      >
                        <ChevronRight aria-hidden />
                      </Button>
                    </div>
                  ) : null}
                </div>
              </div>
            </div>
          )}
          <div className="flex flex-wrap items-center justify-between gap-4 border-t pt-4">
            <div className="flex min-w-0 flex-1 items-start gap-3">
              <Switch
                id="auto-skill-cleanup"
                checked={cleanup.data?.enabled ?? true}
                onCheckedChange={(enabled) => policy.mutate(enabled)}
                disabled={busy || !cleanup.data}
                className="mt-1"
              />
              <div>
                <label
                  htmlFor="auto-skill-cleanup"
                  className="cursor-pointer text-sm font-medium"
                >
                  {copy.keep_skills_clean_automatically}
                </label>
                <p className="mt-1 max-w-prose text-xs leading-relaxed text-muted-foreground">
                  {copy.cleanupHelp}
                </p>
              </div>
            </div>
            <Button
              variant="outline"
              disabled={busy}
              onClick={() => setCleaning(true)}
            >
              <Sparkles aria-hidden />
              {copy.review_cleanup}
            </Button>
          </div>
          {suppressed.isError ? (
            <p role="alert" className="text-sm text-destructive">
              {copy.removed_skills_could_not_be_loaded}
              <Button variant="link" onClick={() => void suppressed.refetch()}>
                Try again
              </Button>
            </p>
          ) : suppressed.data?.length ? (
            <details className="border-t pt-4">
              <summary className="cursor-pointer text-sm font-medium outline-none focus-visible:ring-2 focus-visible:ring-ring">
                {`Removed skills (${suppressed.data.length})`}
              </summary>
              <p className="mt-2 text-xs text-muted-foreground">
                {copy.restoreHelp}
              </p>
              <ul className="mt-3 flex flex-wrap gap-2">
                {suppressed.data.map((skill) => (
                  <li key={skill.token}>
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-auto min-h-9 max-w-full whitespace-normal text-left"
                      disabled={busy}
                      aria-label={`Restore ${skill.display}`}
                      onClick={() => restore.mutate(skill.token)}
                    >
                      <Undo2 aria-hidden />
                      {skill.display}
                    </Button>
                  </li>
                ))}
              </ul>
            </details>
          ) : null}
        </>
      )}
      {editor ? (
        <SkillEditorDialog
          key={editor === "new" ? "new" : editor.key}
          row={editor === "new" ? undefined : editor}
          groups={groups}
          initialGroup={editor === "new" ? newSkillGroup : undefined}
          returnFocus={editorFocus}
          disabled={disabled || rebuilding}
          onClose={() => setEditor(null)}
        />
      ) : null}
      {organizing ? (
        <SkillOrganizationDialog
          groups={groups}
          categories={categories}
          onClose={() => setOrganizing(false)}
          disabled={disabled || rebuilding}
        />
      ) : null}
      {cleaning ? <CleanupDialog onClose={() => setCleaning(false)} /> : null}
      {merging ? (
        <MergeDialog
          rows={selectedRows}
          onClose={() => {
            setMerging(false);
            setSelected(new Set());
          }}
        />
      ) : null}
    </section>
  );
}
