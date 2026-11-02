import { useId, useRef, useState, type FormEvent } from "react";
import {
  FolderPlus,
  MoreHorizontal,
  Pencil,
  Plus,
  Trash2,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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
} from "./SkillEditorFields";
import { SkillMoveForm, skillPopoverClass } from "./SkillContextPopover";
import { useSkillOrganization } from "./use-profile-skills";

type Mode = "actions" | "edit" | "delete" | "new-group" | "new-category";

export function SkillContainerPopover({
  kind,
  item,
  groups,
  categories,
  disabled,
  onAddSkill,
  moveRow,
  onMoveDone,
  create,
}: {
  kind: "group" | "category";
  item: LibraryCategory | LibraryGroup;
  groups: LibraryGroup[];
  categories: LibraryCategory[];
  disabled: boolean;
  onAddSkill: (group: string, trigger?: HTMLElement | null) => void;
  moveRow?: LibraryRow;
  onMoveDone?: () => void;
  create?: "group" | "category";
}) {
  const copy = useSkillCopy();
  const id = useId();
  const trigger = useRef<HTMLButtonElement>(null);
  const handoff = useRef(false);
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<Mode>("actions");
  const [name, setName] = useState("");
  const [parent, setParent] = useState(
    kind === "group" ? (item as LibraryGroup).category : item.slug,
  );
  const mutation = useSkillOrganization();
  const pending = disabled || mutation.isPending;
  function close() {
    setOpen(false);
    setMode("actions");
    onMoveDone?.();
  }
  function edit(next: Mode) {
    mutation.reset();
    setMode(next);
    setName(next === "edit" || next === "delete" ? item.label : "");
    setParent(kind === "group" ? (item as LibraryGroup).category : item.slug);
  }
  function submit(event: FormEvent) {
    event.preventDefault();
    if (pending || !name.trim()) return;
    mutation.mutate(
      {
        kind:
          mode === "new-group"
            ? "group"
            : mode === "new-category"
              ? "category"
              : kind,
        key: mode === "edit" || mode === "delete" ? item.slug : undefined,
        label: name.trim(),
        category: parent || "other",
        remove: mode === "delete",
      },
      {
        onSuccess: () => {
          if (moveRow && mode === "new-group") setMode("actions");
          else close();
        },
      },
    );
  }
  const editingGroup =
    mode === "new-group" || (mode === "edit" && kind === "group");
  const destinationGroups =
    kind === "category"
      ? groups.filter((group) => group.category === item.slug)
      : [];
  const title =
    mode === "new-category"
      ? copy.createCategory
      : mode === "new-group"
        ? copy.createGroup
        : mode === "edit"
          ? kind === "group"
            ? copy.editGroup
            : copy.editCategory
          : mode === "delete"
            ? kind === "group"
              ? copy.deleteGroup
              : copy.deleteCategory
            : item.label;
  return (
    <Popover
      open={open || !!moveRow}
      onOpenChange={(next) => {
        if (mutation.isPending) return;
        if (next) {
          handoff.current = false;
          setOpen(true);
          if (create) edit(create === "group" ? "new-group" : "new-category");
        } else close();
      }}
    >
      {/* Reading a context remains available while its mutation controls are busy. */}
      <PopoverTrigger
        ref={trigger}
        id={
          create
            ? undefined
            : `profile-${kind}-context-${encodeURIComponent(item.slug)}`
        }
        render={
          <Button
            size={create ? "sm" : "icon-sm"}
            variant={create ? "outline" : "ghost"}
          />
        }
        disabled={!!create && disabled}
        aria-label={
          create
            ? create === "group"
              ? copy.add_group
              : copy.add_category
            : kind === "category"
              ? copy.categoryActions(item.label)
              : copy.groupActions(item.label)
        }
      >
        {create ? (
          <>
            <Plus aria-hidden />
            {create === "group" ? copy.add_group : copy.add_category}
          </>
        ) : (
          <MoreHorizontal aria-hidden />
        )}
      </PopoverTrigger>
      <PopoverContent
        align="end"
        className={skillPopoverClass}
        finalFocus={() => (handoff.current ? false : true)}
      >
        <PopoverHeader>
          <div className="flex items-start gap-2">
            <PopoverTitle className="min-w-0 flex-1 leading-snug">
              {title}
            </PopoverTitle>
            <Button
              size="icon-xs"
              variant="ghost"
              disabled={mutation.isPending}
              aria-label={copy.close}
              onClick={close}
            >
              <X aria-hidden />
            </Button>
          </div>
          <PopoverDescription>
            {moveRow && mode === "actions"
              ? copy.chooseDestination
              : copy.containerHelp}
          </PopoverDescription>
        </PopoverHeader>
        {mode === "actions" ? (
          moveRow ? (
            <>
              <p className="text-sm font-medium">{moveRow.display}</p>
              {destinationGroups.length ? (
                <SkillMoveForm
                  row={moveRow}
                  groups={destinationGroups}
                  categories={categories}
                  disabled={pending}
                  onDone={close}
                />
              ) : (
                <>
                  <p className="text-xs text-muted-foreground">
                    {copy.noDestination}
                  </p>
                  <Button
                    variant="outline"
                    disabled={pending}
                    onClick={() => edit("new-group")}
                  >
                    <FolderPlus aria-hidden />
                    {copy.add_group}
                  </Button>
                </>
              )}
            </>
          ) : (
            <div className="grid gap-1">
              {kind === "group" ? (
                <Button
                  variant="ghost"
                  className="justify-start"
                  disabled={pending}
                  onClick={() => {
                    handoff.current = true;
                    close();
                    onAddSkill(item.slug, trigger.current);
                  }}
                >
                  <Plus aria-hidden />
                  {copy.addSkill}
                </Button>
              ) : (
                <Button
                  variant="ghost"
                  className="justify-start"
                  disabled={pending}
                  onClick={() => edit("new-group")}
                >
                  <FolderPlus aria-hidden />
                  {copy.add_group}
                </Button>
              )}
              <Button
                variant="ghost"
                className="justify-start"
                disabled={pending}
                onClick={() => edit("edit")}
              >
                <Pencil aria-hidden />
                {kind === "group" ? copy.editGroup : copy.editCategory}
              </Button>
              <Button
                variant="ghost"
                className="justify-start"
                disabled={pending}
                onClick={() =>
                  edit(kind === "category" ? "new-category" : "new-group")
                }
              >
                <Plus aria-hidden />
                {kind === "category" ? copy.add_category : copy.add_group}
              </Button>
              <Button
                variant="ghost"
                className="justify-start text-destructive"
                disabled={pending || item.slug === "other"}
                onClick={() => edit("delete")}
              >
                <Trash2 aria-hidden />
                {kind === "group" ? copy.deleteGroup : copy.deleteCategory}
              </Button>
              {item.slug === "other" ? (
                <p className="px-2 pt-2 text-xs text-muted-foreground">
                  {copy.fallbackHelp}
                </p>
              ) : null}
            </div>
          )
        ) : (
          <form onSubmit={submit} className="grid min-w-0 gap-3">
            {mode === "delete" ? (
              <p className="text-sm text-muted-foreground">{copy.deleteHelp}</p>
            ) : (
              <>
                <label htmlFor={`${id}-name`} className="text-xs font-medium">
                  {copy.name}
                </label>
                <Input
                  id={`${id}-name`}
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  maxLength={80}
                  required
                  disabled={pending}
                  autoFocus
                />
                {editingGroup ? (
                  <>
                    <label
                      htmlFor={`${id}-category`}
                      className="text-xs font-medium"
                    >
                      {copy.category}
                    </label>
                    <LibrarySelect
                      id={`${id}-category`}
                      value={parent || "other"}
                      onChange={setParent}
                      disabled={pending}
                    >
                      {categories.map((category) => (
                        <option key={category.slug} value={category.slug}>
                          {category.label}
                        </option>
                      ))}
                    </LibrarySelect>
                  </>
                ) : null}
              </>
            )}
            {mutation.error ? (
              <p role="alert" className="text-xs text-destructive">
                {mutation.error.message}
              </p>
            ) : null}
            <div className="flex flex-wrap justify-end gap-2">
              <Button
                type="button"
                variant="outline"
                disabled={pending}
                onClick={() => (create ? close() : setMode("actions"))}
              >
                {copy.cancel}
              </Button>
              <Button
                type="submit"
                variant={mode === "delete" ? "destructive" : "default"}
                disabled={pending || !name.trim()}
              >
                {mutation.isPending
                  ? copy.saving
                  : mode === "delete"
                    ? copy.delete
                    : mode === "new-group"
                      ? copy.add_group
                      : mode === "new-category"
                        ? copy.add_category
                        : copy.save}
              </Button>
            </div>
          </form>
        )}
      </PopoverContent>
    </Popover>
  );
}
