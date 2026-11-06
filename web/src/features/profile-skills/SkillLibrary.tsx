import { useSkillCopy } from "@/i18n/skill-copy";
import { useId, useState } from "react";
import { useIsMutating } from "@tanstack/react-query";
import {
  Check,
  CircleAlert,
  FolderCog,
  LayoutGrid,
  List,
  ListFilter,
  GitMerge,
  Plus,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ListSearch } from "@/components/ui/list-search";
import { SearchableSelect } from "@/components/ui/searchable-select";
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
import { listSearch } from "@/lib/list-search";
import { cn } from "@/lib/utils";
import {
  localizeSkillContainer,
  localizeSkillLabel,
} from "@/i18n/skill-labels";
import {
  LibrarySelect,
  type LibraryRow,
} from "./SkillEditorFields";
import { SkillEditorDialog } from "./SkillEditorDialog";
import { SkillCompactView } from "./SkillCompactView";
import { SkillDetailedView } from "./SkillDetailedView";
import { SkillOrganizationDialog } from "./SkillOrganizationDialog";
import { RemovedSkillList } from "./RemovedSkillList";
import { buildSkillTree, type SkillDisclosure } from "./skill-tree";
import { skillGroupOptions } from "./skill-group-options";
import {
  SKILL_MUTATION_KEY,
  useCleanProfileSkills,
  useMergeProfileSkills,
  useSkillCleanup,
  useSkillCleanupPolicy,
} from "./use-profile-skills";

const ACTIVE = ["queued", "running", "cancelling"];
const OTHER_SLUG = "other";

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
  const { t, i18n } = useTranslation();
  const searchId = useId();
  const filterId = useId();
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
  const [disclosures, setDisclosures] = useState<Record<string, boolean>>({});
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [categoryFilter, setCategory] = useState("all");
  const [groupFilter, setGroup] = useState("all");
  const [origin, setOrigin] = useState("all");
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
  const fallback = { slug: OTHER_SLUG, label: "Other", customized: false };
  const localize = <T extends { label: string; customized?: boolean }>(item: T) => ({
    ...localizeSkillContainer(item, i18n.resolvedLanguage),
    originalLabel: item.label,
  });
  const categories = (matrix.data.categories ?? []).map(localize);
  const categorySlugs = new Set(categories.map((item) => item.slug));
  const groups = (matrix.data.groups ?? []).map((item) => localize({
    ...item,
    category: categorySlugs.has(item.category) ? item.category : fallback.slug,
  }));
  const byGroup = new Map(groups.map((item) => [item.slug, item]));
  if (!byGroup.has("other") && rows.some((row) => !byGroup.has(row.group ?? "other"))) {
    const other = localize({ ...fallback, category: "other" });
    groups.push(other);
    byGroup.set(other.slug, other);
  }
  if (!categorySlugs.has("other") && (!categories.length || groups.some((item) => item.category === "other"))) {
    categories.push(localize(fallback));
  }
  const byCategory = new Map(categories.map((item) => [item.slug, item]));
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
  const groupOf = (row: LibraryRow) => byGroup.get(row.group ?? "other")?.slug ?? "other";
  const matches = listSearch(search);
  const filtered = rows.filter((row) => {
    const owner = byGroup.get(groupOf(row));
    const parent = byCategory.get(owner?.category ?? "other");
    return (category === "all" || parent?.slug === category) &&
      (group === "all" || owner?.slug === group) &&
      (origin === "all" || row.inferred === (origin === "inferred")) &&
      matches(row.display, row.key, owner?.label, owner?.originalLabel, parent?.label, parent?.originalLabel, ...(row.aliases ?? []));
  });
  const hasSearch = !!search.trim();
  const hasFilters = category !== "all" || group !== "all" || origin !== "all";
  const filterScope = hasSearch || hasFilters ? JSON.stringify([search.trim(), category, group, origin]) : "";
  const tree = buildSkillTree(categories, groups, filtered, groupOf, {
    category,
    group,
    showEmpty: view === "compact" && !hasSearch && origin === "all",
  });
  const disclosure: SkillDisclosure = (kind, slug) => {
    const key = `${kind}:${slug}`;
    return {
      browseOpen: disclosures[key],
      onBrowseOpenChange: (open) => setDisclosures((current) => ({ ...current, [key]: open })),
    };
  };
  const selectedRows = rows.filter((row) => selected.has(row.key));
  const built = !!matrix.data.generatedAt;
  const unclassified =
    run?.result && "unclassified" in run.result ? run.result.unclassified : 0;
  const chooseCategory = (slug: string) => {
    setCategory(slug);
    setGroup("all");
  };
  function clearFilters() {
    setSearch("");
    chooseCategory("all");
    setOrigin("all");
    document.getElementById(searchId)?.focus();
  }
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
  function selectPage(visible: LibraryRow[], checked: boolean) {
    setSelected((previous) => {
      const next = new Set(previous);
      for (const row of visible) {
        if (checked) next.add(row.key);
        else next.delete(row.key);
      }
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
    <div className="flex min-w-0 flex-wrap items-start gap-2">
      <ListSearch id={searchId} value={search} onChange={setSearch} aria-label={copy.searchLibrary} placeholder={copy.searchLibrary} className="flex-[1_1_12rem]" />
      <Button
        type="button"
        variant={hasFilters ? "secondary" : "outline"}
        size="icon"
        className="size-11 self-stretch @3xl/library:hidden"
        aria-label={copy.skillFilters}
        aria-expanded={filtersOpen}
        aria-controls={filterId}
        onClick={() => setFiltersOpen(!filtersOpen)}
      >
        <ListFilter aria-hidden />
      </Button>
      <div id={filterId} className={cn("w-full min-w-0 flex-wrap items-center gap-2 @3xl/library:flex @3xl/library:w-auto [&_select]:h-11", filtersOpen ? "flex" : "hidden")}>
        <LibrarySelect value={category} onChange={chooseCategory} label={copy.skill_categories}>
          <option value="all">{copy.all_skills}</option>
          {categories.map((item) => <option key={item.slug} value={item.slug}>{item.label}</option>)}
        </LibrarySelect>
        <SearchableSelect
          label={copy.filter_by_group}
          searchLabel={copy.searchOrganization}
          className="min-h-11 w-auto max-w-full"
          value={group}
          onChange={setGroup}
          groups={[
            { id: "all-groups", items: [{ value: "all", label: copy.all_groups }] },
            ...skillGroupOptions(groups.filter((item) => category === "all" || item.category === category), categories),
          ]}
        />
        <LibrarySelect value={origin} onChange={setOrigin} label={copy.filter_by_evidence}>
          <option value="all">{copy.all_evidence}</option>
          <option value="literal">{copy.listed_skills}</option>
          <option value="inferred">{copy.inferred_skills}</option>
        </LibrarySelect>
      </div>
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
            className="sr-only"
          >
            {copy.your_skill_library}
          </h2>
          <p className="text-sm text-muted-foreground">{`${rows.length} skills · ${groups.length} groups`}</p>
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
          {filters}
          <p role="status" className="text-sm text-muted-foreground empty:sr-only">
            {hasSearch || hasFilters ? t("longLists.results", { shown: filtered.length, total: rows.length }) : null}
          </p>
          {selectionBar}
          {!tree.length ? (
            <div className="rounded-lg border border-dashed px-4 py-8 text-center">
              <p className="font-medium">{rows.length ? copy.noMatchingSkills : copy.no_skills_yet}</p>
              <p className="mt-1 text-sm text-muted-foreground">{rows.length ? copy.noMatches : copy.noSkills}</p>
              {filterScope ? (
                <Button type="button" variant="ghost" className="mt-2" onClick={clearFilters}>{copy.clear_filters}</Button>
              ) : null}
            </div>
          ) : view === "compact" ? (
            <SkillCompactView
              tree={tree}
              groups={groups}
              categories={categories}
              disabled={busy}
              focusedCategory={category !== "all"}
              query={filterScope}
              disclosure={disclosure}
              showAliases={hasSearch}
              selected={selected}
              onEdit={openEditor}
              onDelete={(key) => remove.mutate(key)}
              onAdd={addToGroup}
              onSelect={toggleSelection}
            />
          ) : (
            <SkillDetailedView
              tree={tree}
              groups={groups}
              categories={categories}
              disabled={busy}
              focusedCategory={category !== "all"}
              query={filterScope}
              disclosure={disclosure}
              selected={selected}
              onEdit={openEditor}
              onDelete={(key) => remove.mutate(key)}
              onSelect={toggleSelection}
              onSelectPage={selectPage}
            />
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
            <RemovedSkillList
              skills={suppressed.data}
              disabled={busy}
              onRestore={(token) => restore.mutate(token)}
            />
          ) : null}
        </>
      )}
      {editor ? (
        <SkillEditorDialog
          key={editor === "new" ? "new" : editor.key}
          row={editor === "new" ? undefined : editor}
          groups={groups}
          categories={categories}
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
