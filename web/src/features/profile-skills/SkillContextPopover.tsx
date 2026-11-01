import { useId, useRef, useState, type FormEvent } from "react";
import {
  Check,
  GitMerge,
  MoveRight,
  Pencil,
  Trash2,
  Undo2,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverDescription,
  PopoverHeader,
  PopoverTitle,
  PopoverTrigger,
} from "@/components/ui/popover";
import { useSkillCopy } from "@/i18n/skill-copy";
import {
  LibrarySelect,
  type LibraryCategory,
  type LibraryGroup,
  type LibraryRow,
} from "./SkillEditorDialog";
import { SKILL_CATEGORY_LABELS, skillCategoryValue } from "./skill-categories";
import { useMoveSkillGroup } from "./use-profile-skills";

export const skillPopoverClass =
  "w-80 max-w-[calc(100vw-2rem)] max-h-(--available-height) overflow-y-auto animate-none transition-none duration-0 data-open:animate-none data-closed:animate-none [overflow-wrap:anywhere] [&_[data-slot=button]]:h-auto [&_[data-slot=button]]:min-h-9 [&_[data-slot=button]]:max-w-full [&_[data-slot=button]]:whitespace-normal";
const actionClass = "h-auto min-h-9 w-full justify-start whitespace-normal";

export function SkillMoveForm({
  row,
  groups,
  categories,
  disabled,
  onDone,
}: {
  row: LibraryRow;
  groups: LibraryGroup[];
  categories: LibraryCategory[];
  disabled: boolean;
  onDone: () => void;
}) {
  const copy = useSkillCopy();
  const id = useId();
  const [chosen, setChosen] = useState("");
  const move = useMoveSkillGroup();
  const destination =
    chosen ||
    (row.group && groups.some((g) => g.slug === row.group) && row.group) ||
    groups[0]?.slug ||
    "";
  function submit(event: FormEvent) {
    event.preventDefault();
    if (destination && !disabled && !move.isPending)
      move.mutate({ key: row.key, group: destination }, { onSuccess: onDone });
  }
  return (
    <form className="grid min-w-0 gap-3" onSubmit={submit}>
      <label htmlFor={id} className="text-xs font-medium">
        {copy.moveTo}
      </label>
      <LibrarySelect
        id={id}
        value={destination}
        onChange={setChosen}
        disabled={disabled || move.isPending}
      >
        {categories.map((category) => (
          <optgroup key={category.slug} label={category.label}>
            {groups
              .filter((group) => group.category === category.slug)
              .map((group) => (
                <option key={group.slug} value={group.slug}>
                  {group.label}
                </option>
              ))}
          </optgroup>
        ))}
      </LibrarySelect>
      {move.error ? (
        <p role="alert" className="text-xs text-destructive">
          {move.error.message}
        </p>
      ) : null}
      <Button
        type="submit"
        disabled={
          disabled ||
          move.isPending ||
          !destination ||
          (destination === row.group && row.groupSource === "correction")
        }
      >
        <MoveRight aria-hidden />
        {move.isPending ? copy.saving : copy.moveSkill}
      </Button>
      {row.groupSource === "correction" ? (
        <Button
          type="button"
          variant="ghost"
          disabled={disabled || move.isPending}
          onClick={() =>
            move.mutate({ key: row.key, group: null }, { onSuccess: onDone })
          }
        >
          <Undo2 aria-hidden />
          {copy.resetGrouping}
        </Button>
      ) : null}
    </form>
  );
}

export function SkillContextPopover({
  row,
  groups,
  categories,
  disabled,
  selected,
  compact = false,
  onEdit,
  onDelete,
  onSelect,
}: {
  row: LibraryRow;
  groups: LibraryGroup[];
  categories: LibraryCategory[];
  disabled: boolean;
  selected: boolean;
  compact?: boolean;
  onEdit: (row: LibraryRow, trigger: HTMLElement | null) => void;
  onDelete: (key: string) => void;
  onSelect: (key: string) => void;
}) {
  const copy = useSkillCopy();
  const trigger = useRef<HTMLButtonElement>(null);
  const handoff = useRef(false);
  const [open, setOpen] = useState(false);
  const kind = skillCategoryValue(row.category);
  return (
    <Popover
      open={open}
      onOpenChange={(next) => {
        if (next) handoff.current = false;
        setOpen(next);
      }}
    >
      {/* Keep the reading surface and return-focus target available during saves. */}
      <PopoverTrigger
        ref={trigger}
        id={`profile-skill-${encodeURIComponent(row.key)}`}
        render={
          <button
            type="button"
            className={
              compact
                ? "min-w-0 max-w-full px-2 py-1.5 text-left text-xs font-medium outline-none [overflow-wrap:anywhere] focus-visible:rounded-md focus-visible:ring-2 focus-visible:ring-ring"
                : "min-w-0 max-w-full text-left text-sm font-medium underline-offset-4 outline-none [overflow-wrap:anywhere] hover:underline focus-visible:rounded focus-visible:ring-2 focus-visible:ring-ring"
            }
          />
        }
      >
        {row.display}
      </PopoverTrigger>
      <PopoverContent
        align="start"
        className={skillPopoverClass}
        finalFocus={() => (handoff.current ? false : true)}
      >
        <PopoverHeader>
          <div className="flex min-w-0 items-start gap-2">
            <PopoverTitle className="min-w-0 flex-1 leading-snug">
              {row.display}
            </PopoverTitle>
            <Button
              variant="ghost"
              size="icon-xs"
              aria-label={copy.close}
              onClick={() => setOpen(false)}
            >
              <X aria-hidden />
            </Button>
          </div>
          <PopoverDescription>
            {row.inferred
              ? copy.linked_to_profile_evidence
              : copy.listed_in_your_profile}
          </PopoverDescription>
        </PopoverHeader>
        {row.aliases?.length ? (
          <p className="text-xs leading-relaxed text-muted-foreground">
            {row.aliases.join(", ")}
          </p>
        ) : null}
        <dl className="flex flex-wrap items-center justify-between gap-2 text-xs">
          <dt className="text-muted-foreground">{copy.type}</dt>
          <dd>{SKILL_CATEGORY_LABELS[kind]}</dd>
        </dl>
        <SkillMoveForm
          row={row}
          groups={groups}
          categories={categories}
          disabled={disabled}
          onDone={() => setOpen(false)}
        />
        <div className="-mx-4 border-t px-2 pt-2">
          <Button
            variant="ghost"
            className={actionClass}
            disabled={disabled}
            onClick={() => {
              handoff.current = true;
              setOpen(false);
              onEdit(row, trigger.current);
            }}
          >
            <Pencil aria-hidden />
            {copy.edit_skill}
          </Button>
          <Button
            variant="ghost"
            className={actionClass}
            disabled={disabled}
            aria-pressed={selected}
            onClick={() => {
              onSelect(row.key);
              setOpen(false);
            }}
          >
            {selected ? <Check aria-hidden /> : <GitMerge aria-hidden />}
            {selected ? copy.unselectMerge : copy.selectMerge}
          </Button>
          <Button
            variant="ghost"
            className={`${actionClass} text-destructive`}
            disabled={disabled}
            onClick={() => {
              setOpen(false);
              onDelete(row.key);
            }}
          >
            <Trash2 aria-hidden />
            {copy.delete}
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
