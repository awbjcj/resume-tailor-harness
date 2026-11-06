import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Check, GripVertical, MoveRight, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ListSection } from "@/components/ui/list-section";
import { useSkillCopy } from "@/i18n/skill-copy";
import { cn } from "@/lib/utils";
import type {
  LibraryCategory,
  LibraryGroup,
  LibraryRow,
} from "./SkillEditorFields";
import { SkillContainerPopover } from "./SkillContainerPopover";
import { SkillContextPopover } from "./SkillContextPopover";
import { useMoveSkillGroup } from "./use-profile-skills";
import { useSkillDrag, type SkillDropTarget } from "./use-skill-drag";
import type { SkillBranch, SkillDisclosure } from "./skill-tree";

const CHIP_BATCH = 48;

export function SkillCompactView({
  tree,
  groups,
  categories,
  disabled,
  focusedCategory,
  query,
  disclosure,
  showAliases,
  selected,
  onEdit,
  onDelete,
  onAdd,
  onSelect,
}: {
  tree: SkillBranch[];
  groups: LibraryGroup[];
  categories: LibraryCategory[];
  disabled: boolean;
  focusedCategory: boolean;
  query: string;
  disclosure: SkillDisclosure;
  showAliases: boolean;
  selected: Set<string>;
  onEdit: (row: LibraryRow, trigger: HTMLElement | null) => void;
  onDelete: (key: string) => void;
  onAdd: (group: string, trigger?: HTMLElement | null) => void;
  onSelect: (key: string) => void;
}) {
  const copy = useSkillCopy();
  const { t } = useTranslation();
  const [limits, setLimits] = useState<Record<string, number>>({});
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
  const shortList = tree.reduce((total, branch) => total + branch.count, 0) <= 50;
  return (
    <div
      className="min-w-0 space-y-2"
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
      {tree.map(({ category: container, groups: children, count }) => {
        const active = target?.kind === "category" && target.key === container.slug;
        return (
          <ListSection
            key={container.slug}
            label={container.label}
            count={count}
            defaultOpen={shortList || focusedCategory || tree.length === 1}
            query={query}
            {...disclosure("category", container.slug)}
            data-skill-drop-category={container.slug}
            aria-label={container.label}
            className={cn("rounded-lg border bg-muted/25", active && "border-primary ring-2 ring-primary/30")}
            actions={
              <div className="flex items-center gap-2 pr-2">
                {active ? <span className="text-xs text-primary">{copy.moveHere}</span> : null}
                <SkillContainerPopover
                  kind="category"
                  item={container}
                  groups={groups}
                  categories={categories}
                  disabled={disabled}
                  onAddSkill={onAdd}
                  moveRow={categoryMove?.category === container.slug ? categoryMove.row : undefined}
                  onMoveDone={() => setCategoryMove(null)}
                />
              </div>
            }
          >
            <div className="min-w-0 space-y-2 px-2 pb-2 sm:px-3 sm:pb-3">
              {children.map(({ group: child, rows: skills }) => {
                const over = target?.kind === "group" && target.key === child.slug;
                const limit = limits[child.slug] ?? CHIP_BATCH;
                return (
                  <ListSection
                    key={child.slug}
                    level={4}
                    label={child.label}
                    count={skills.length}
                    defaultOpen={shortList || children.length === 1}
                    query={query}
                    {...disclosure("group", child.slug)}
                    data-skill-drop-group={child.slug}
                    aria-label={child.label}
                    className={cn(
                      "rounded-md border border-border bg-card",
                      over && "border-primary bg-primary/5 ring-1 ring-primary/30",
                    )}
                    actions={
                      <div className="pr-2">
                        <SkillContainerPopover
                          kind="group"
                          item={child}
                          groups={groups}
                          categories={categories}
                          disabled={disabled}
                          onAddSkill={onAdd}
                        />
                      </div>
                    }
                  >
                    <div className="flex min-w-0 flex-wrap content-start items-start gap-1.5 border-t px-3 py-2.5">
                      {skills.slice(0, limit).map((row) => (
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
                          <div className="min-w-0">
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
                            {showAliases && row.aliases?.length ? (
                              <span className="block px-2 pb-1.5 text-xs text-muted-foreground [overflow-wrap:anywhere]">{row.aliases.join(", ")}</span>
                            ) : null}
                          </div>
                          {row.inferred ? (
                            <span
                              aria-hidden
                              className="mr-2 size-1.5 shrink-0 rounded-full bg-muted-foreground/70"
                              title={copy.inferred}
                            />
                          ) : null}
                        </div>
                      ))}
                      {skills.length > limit ? (
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() => {
                            setLimits((current) => ({ ...current, [child.slug]: limit + CHIP_BATCH }));
                            requestAnimationFrame(() => {
                              document.getElementById(`profile-skill-${encodeURIComponent(skills[limit].key)}`)?.focus();
                            });
                          }}
                        >
                          {t("longLists.showMore", { count: Math.min(CHIP_BATCH, skills.length - limit) })}
                        </Button>
                      ) : null}
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
                  </ListSection>
                );
              })}
              {!children.length ? (
                <div className="flex min-w-0 flex-wrap items-center justify-between gap-3 rounded-lg border border-dashed px-4 py-3">
                  <p className="text-xs text-muted-foreground">{copy.noDestination}</p>
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
          </ListSection>
        );
      })}
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
