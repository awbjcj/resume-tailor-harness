import { useState } from "react";
import { ChevronLeft, ChevronRight, Pencil, Trash2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { ListSection } from "@/components/ui/list-section";
import { useSkillCopy } from "@/i18n/skill-copy";
import { SkillContextPopover } from "./SkillContextPopover";
import type { LibraryCategory, LibraryGroup, LibraryRow } from "./SkillEditorFields";
import type { SkillBranch, SkillDisclosure } from "./skill-tree";

const PAGE_SIZE = 40;

type RowActions = {
  categories: LibraryCategory[];
  groups: LibraryGroup[];
  selected: Set<string>;
  disabled: boolean;
  onEdit: (row: LibraryRow, trigger: HTMLElement | null) => void;
  onDelete: (key: string) => void;
  onSelect: (key: string) => void;
  onSelectPage: (rows: LibraryRow[], checked: boolean) => void;
};

function SkillRows({
  rows,
  groupLabel,
  searching,
  groups,
  categories,
  selected,
  disabled,
  onEdit,
  onDelete,
  onSelect,
  onSelectPage,
}: RowActions & { rows: LibraryRow[]; groupLabel: string; searching: boolean }) {
  const copy = useSkillCopy();
  const [page, setPage] = useState(0);
  const pages = Math.ceil(rows.length / PAGE_SIZE);
  const safePage = Math.min(page, pages - 1);
  const visible = rows.slice(safePage * PAGE_SIZE, (safePage + 1) * PAGE_SIZE);
  const selectedCount = visible.filter((row) => selected.has(row.key)).length;
  return (
    <>
      {rows.length > 1 ? (
        <div className="flex min-w-0 flex-wrap items-center justify-between gap-x-3 gap-y-1 border-t px-3 py-1.5">
          <label className="flex min-h-11 cursor-pointer items-center gap-2 text-xs text-muted-foreground sm:min-h-9">
            <Checkbox
              aria-label={copy.selectGroupSkills(groupLabel)}
              disabled={disabled}
              checked={selectedCount === visible.length}
              indeterminate={selectedCount > 0 && selectedCount < visible.length}
              onCheckedChange={(checked) => onSelectPage(visible, checked)}
            />
            {copy.select_visible_skills}
          </label>
          {pages > 1 ? (
            <div className="flex items-center gap-1">
              <Button type="button" variant="ghost" size="icon" className="size-11 sm:size-9" aria-label={copy.previous_skills_page} disabled={safePage === 0} onClick={() => setPage(safePage - 1)}>
                <ChevronLeft aria-hidden />
              </Button>
              <span aria-live="polite" className="px-1 text-xs tabular-nums text-muted-foreground">{safePage + 1} / {pages}</span>
              <Button type="button" variant="ghost" size="icon" className="size-11 sm:size-9" aria-label={copy.next_skills_page} disabled={safePage === pages - 1} onClick={() => setPage(safePage + 1)}>
                <ChevronRight aria-hidden />
              </Button>
            </div>
          ) : null}
        </div>
      ) : null}
      <ul className="divide-y border-t">
        {visible.map((row) => (
          <li key={row.key} className="grid min-w-0 grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-x-2 gap-y-1 px-3 py-2 sm:gap-x-3">
            <Checkbox aria-label={copy.selectSkill(row.display)} checked={selected.has(row.key)} disabled={disabled} onCheckedChange={() => onSelect(row.key)} />
            <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
              <SkillContextPopover
                row={row}
                groups={groups}
                categories={categories}
                disabled={disabled}
                selected={selected.has(row.key)}
                onEdit={onEdit}
                onDelete={onDelete}
                onSelect={onSelect}
              />
              {row.inferred ? <Badge variant="outline" className="text-xs">{copy.inferred}</Badge> : null}
            </div>
            <div className="flex shrink-0">
              <Button type="button" variant="ghost" size="icon" className="size-11 sm:size-9" aria-label={copy.editSkillAction(row.display)} disabled={disabled} onClick={(event) => onEdit(row, event.currentTarget)}>
                <Pencil aria-hidden />
              </Button>
              <Button type="button" variant="ghost" size="icon" aria-label={copy.deleteSkillAction(row.display)} className="size-11 text-destructive hover:bg-destructive/10 hover:text-destructive sm:size-9" disabled={disabled} onClick={() => onDelete(row.key)}>
                <Trash2 aria-hidden />
              </Button>
            </div>
            {row.aliases?.length || row.groupSource === "correction" ? (
              <div className="col-span-2 col-start-2 min-w-0 space-y-0.5 pb-1 text-xs leading-relaxed text-muted-foreground [overflow-wrap:anywhere]">
                {row.aliases?.length ? <p className={searching ? undefined : "line-clamp-2"}>{row.aliases.join(", ")}</p> : null}
                {row.groupSource === "correction" ? <p>{copy.manually_assigned}</p> : null}
              </div>
            ) : null}
          </li>
        ))}
      </ul>
    </>
  );
}

export function SkillDetailedView({
  tree,
  query,
  focusedCategory,
  disclosure,
  ...actions
}: RowActions & { tree: SkillBranch[]; query: string; focusedCategory: boolean; disclosure: SkillDisclosure }) {
  const shortList = tree.reduce((total, branch) => total + branch.count, 0) <= 20;
  return (
    <div className="min-w-0 space-y-2">
      {tree.map(({ category, groups, count }) => (
        <ListSection key={category.slug} label={category.label} count={count} query={query} defaultOpen={shortList || focusedCategory || tree.length === 1} {...disclosure("category", category.slug)} className="rounded-lg border bg-muted/25">
          <div className="space-y-2 px-2 pb-2 sm:px-3 sm:pb-3">
            {groups.map(({ group, rows }) => (
              <ListSection key={group.slug} level={4} label={group.label} count={rows.length} query={query} defaultOpen={shortList || groups.length === 1} {...disclosure("group", group.slug)} className="rounded-md border bg-card">
                <SkillRows key={query} rows={rows} groupLabel={group.label} searching={!!query} {...actions} />
              </ListSection>
            ))}
          </div>
        </ListSection>
      ))}
    </div>
  );
}
