import { useState } from "react";
import { Check, GripVertical, MoveRight, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useSkillCopy } from "@/i18n/skill-copy";
import { cn } from "@/lib/utils";
import type {
  LibraryCategory,
  LibraryGroup,
  LibraryRow,
} from "./SkillEditorDialog";
import { SkillContainerPopover } from "./SkillContainerPopover";
import { SkillContextPopover } from "./SkillContextPopover";
import { useMoveSkillGroup } from "./use-profile-skills";
import { useSkillDrag, type SkillDropTarget } from "./use-skill-drag";

export function SkillCompactView({
  rows,
  allRows,
  groups,
  categories,
  disabled,
  category,
  group,
  hasSearch,
  selected,
  onEdit,
  onDelete,
  onAdd,
  onSelect,
  onClear,
}: {
  rows: LibraryRow[];
  allRows: LibraryRow[];
  groups: LibraryGroup[];
  categories: LibraryCategory[];
  disabled: boolean;
  category: string;
  group: string;
  hasSearch: boolean;
  selected: Set<string>;
  onEdit: (row: LibraryRow, trigger: HTMLElement | null) => void;
  onDelete: (key: string) => void;
  onAdd: (group: string, trigger?: HTMLElement | null) => void;
  onSelect: (key: string) => void;
  onClear: () => void;
}) {
  const copy = useSkillCopy();
  const move = useMoveSkillGroup();
  const [categoryMove, setCategoryMove] = useState<{
    category: string;
    row: LibraryRow;
  } | null>(null);
  const [announcement, setAnnouncement] = useState("");
  function drop(row: LibraryRow, target: SkillDropTarget) {
    if (disabled) return;
    if (target.kind === "category") {
      const destinations = groups.filter((g) => g.category === target.key);
      if (destinations.length !== 1) {
        setCategoryMove({ category: target.key, row });
        return;
      }
      target = { kind: "group", key: destinations[0].slug };
    }
    if (target.key === (row.group ?? "other")) return;
    const label = groups.find((g) => g.slug === target.key)?.label;
    if (!label) return;
    move.mutate(
      { key: row.key, group: target.key },
      { onSuccess: () => setAnnouncement(copy.movedSkill(row.display, label)) },
    );
  }
  const { dragging, target, previewRef, handleProps } = useSkillDrag({
    disabled,
    onDrop: drop,
  });
  const members = new Map<string, LibraryRow[]>();
  const known = new Set(groups.map((g) => g.slug));
  for (const row of rows) {
    const key = row.group && known.has(row.group) ? row.group : "other";
    const bucket = members.get(key) ?? [];
    bucket.push(row);
    members.set(key, bucket);
  }
  const visibleCategories = categories.filter(
    (c) => category === "all" || category === c.slug,
  );
  const validCategories = new Set(categories.map((c) => c.slug));
  const groupCategory = (g: LibraryGroup) =>
    validCategories.has(g.category) ? g.category : "other";
  return (
    <div
      className="min-w-0 space-y-6"
      role="region"
      aria-label={copy.compactView}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <p className="max-w-prose text-xs leading-relaxed text-muted-foreground">
          {copy.compactHelp}
        </p>
        <SkillContainerPopover
          kind="category"
          item={categories[0]}
          groups={groups}
          categories={categories}
          disabled={disabled}
          onAddSkill={onAdd}
          create="category"
        />
      </div>
      <p className="sr-only" role="status" aria-live="polite">
        {dragging ? copy.draggingSkill(dragging.display) : announcement}
      </p>
      {rows.length === 0 && hasSearch ? (
        <div className="rounded-xl border border-dashed py-10 text-center">
          <p className="text-sm text-muted-foreground">{copy.noMatches}</p>
          <Button variant="ghost" onClick={onClear}>
            {copy.clear_filters}
          </Button>
        </div>
      ) : (
        visibleCategories.map((container) => {
          const children = groups.filter(
            (g) =>
              groupCategory(g) === container.slug &&
              (group === "all" || g.slug === group) &&
              (!hasSearch || members.get(g.slug)?.length),
          );
          if ((hasSearch || group !== "all") && !children.length) return null;
          const count = children.reduce(
            (sum, child) => sum + (members.get(child.slug)?.length ?? 0),
            0,
          );
          const active =
            target?.kind === "category" && target.key === container.slug;
          return (
            <section
              key={container.slug}
              data-skill-drop-category={container.slug}
              aria-label={container.label}
              className={cn(
                "min-w-0 rounded-xl outline-2 outline-offset-4 outline-transparent",
                active && "outline-primary/50",
              )}
            >
              <div
                className={cn(
                  "mb-3 flex min-w-0 items-center gap-2 border-b pb-2",
                  active && "border-primary text-primary",
                )}
              >
                <h3 className="min-w-0 flex-1 text-sm font-semibold">
                  {container.label}{" "}
                  <span className="ml-2 font-normal tabular-nums text-muted-foreground">
                    {count}
                  </span>
                </h3>
                {active ? (
                  <span className="text-xs">{copy.moveHere}</span>
                ) : null}
                <SkillContainerPopover
                  kind="category"
                  item={container}
                  groups={groups}
                  categories={categories}
                  disabled={disabled}
                  onAddSkill={onAdd}
                  moveRow={
                    categoryMove?.category === container.slug
                      ? categoryMove.row
                      : undefined
                  }
                  onMoveDone={() => setCategoryMove(null)}
                />
              </div>
              <div className="min-w-0 space-y-2">
                {children.map((child) => {
                  const skills = members.get(child.slug) ?? [];
                  const over =
                    target?.kind === "group" && target.key === child.slug;
                  return (
                    <section
                      key={child.slug}
                      data-skill-drop-group={child.slug}
                      aria-label={child.label}
                      className={cn(
                        "grid min-w-0 grid-cols-1 rounded-xl border border-border bg-card @2xl/library:grid-cols-[12rem_minmax(0,1fr)]",
                        over &&
                          "border-primary bg-primary/5 ring-1 ring-primary/30",
                      )}
                    >
                      <div className="flex min-w-0 items-center gap-2 px-3 py-2 @2xl/library:items-start @2xl/library:border-r">
                        <h4 className="min-w-0 flex-1 py-1 text-xs font-medium leading-relaxed">
                          {child.label}{" "}
                          <span className="ml-2 tabular-nums text-muted-foreground">
                            {skills.length}
                          </span>
                        </h4>
                        <SkillContainerPopover
                          kind="group"
                          item={child}
                          groups={groups}
                          categories={categories}
                          disabled={disabled}
                          onAddSkill={onAdd}
                        />
                      </div>
                      <div className="flex min-w-0 flex-wrap content-start items-start gap-1.5 px-3 pb-3 @2xl/library:py-3">
                        {skills.map((row) => (
                          <div
                            key={row.key}
                            data-skill-chip={row.key}
                            data-selected={selected.has(row.key) || undefined}
                            className={cn(
                              "inline-flex min-w-0 max-w-full items-center rounded-md border border-border bg-background text-foreground",
                              selected.has(row.key) &&
                                "border-primary/60 bg-primary/5",
                              dragging?.key === row.key && "opacity-40",
                            )}
                          >
                            <span
                              aria-hidden="true"
                              data-drag-skill={row.key}
                              title={copy.dragHandleTitle}
                              className={cn(
                                "flex min-h-8 w-6 shrink-0 touch-none select-none items-center justify-center text-muted-foreground",
                                disabled
                                  ? "opacity-40"
                                  : "cursor-grab active:cursor-grabbing",
                              )}
                              {...handleProps(row)}
                            >
                              <GripVertical className="size-3" />
                            </span>
                            {selected.has(row.key) ? (
                              <Check
                                aria-hidden
                                className="size-3 shrink-0 text-primary"
                              />
                            ) : null}
                            <SkillContextPopover
                              row={row}
                              groups={groups}
                              categories={categories}
                              compact
                              disabled={disabled}
                              selected={selected.has(row.key)}
                              onEdit={onEdit}
                              onDelete={onDelete}
                              onSelect={onSelect}
                            />
                            {row.inferred ? (
                              <span
                                aria-hidden
                                className="mr-2 size-1.5 shrink-0 rounded-full bg-muted-foreground/70"
                                title={copy.inferred}
                              />
                            ) : null}
                          </div>
                        ))}
                        {!skills.length ? (
                          <div className="flex w-full items-center justify-between gap-2 py-1">
                            <p className="text-xs leading-relaxed text-muted-foreground">
                              {over ? copy.dropSkill : copy.emptyGroup}
                            </p>
                            <Button
                              size="icon-sm"
                              variant="ghost"
                              aria-label={`${copy.addSkill}: ${child.label}`}
                              disabled={disabled}
                              onClick={(event) =>
                                onAdd(
                                  child.slug,
                                  document.getElementById(
                                    `profile-group-context-${encodeURIComponent(child.slug)}`,
                                  ) ?? event.currentTarget,
                                )
                              }
                            >
                              <Plus aria-hidden />
                            </Button>
                          </div>
                        ) : null}
                      </div>
                    </section>
                  );
                })}
                {!children.length ? (
                  <div className="flex min-w-0 flex-wrap items-center justify-between gap-3 rounded-xl border border-dashed px-4 py-5">
                    <p className="text-xs text-muted-foreground">
                      {copy.noDestination}
                    </p>
                    <SkillContainerPopover
                      kind="category"
                      item={container}
                      groups={groups}
                      categories={categories}
                      disabled={disabled}
                      onAddSkill={onAdd}
                      create="group"
                    />
                  </div>
                ) : null}
              </div>
            </section>
          );
        })
      )}
      {!hasSearch && allRows.length ? (
        <p className="text-xs leading-relaxed text-muted-foreground">
          {copy.dragHelp}
        </p>
      ) : null}
      {dragging && !disabled ? (
        <div
          ref={previewRef}
          aria-hidden
          className="pointer-events-none fixed left-0 top-0 z-[60] flex max-w-[min(18rem,calc(100vw-1rem))] items-center gap-2 rounded-lg bg-popover px-3 py-2 text-sm font-medium text-popover-foreground shadow-card-raised ring-1 ring-primary/30"
        >
          <MoveRight className="size-4 shrink-0 text-primary" />
          <span className="min-w-0 [overflow-wrap:anywhere]">
            {dragging.display}
          </span>
        </div>
      ) : null}
    </div>
  );
}
