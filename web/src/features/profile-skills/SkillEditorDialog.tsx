import { useSkillCopy } from "@/i18n/skill-copy";
import { useId, useState, type FormEvent, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Spinner } from "@/components/ui/spinner";
import type { ProfileMatrix } from "@/features/settings/use-matrix";
import {
  SKILL_CATEGORIES,
  skillCategoryValue,
  type SkillCategory,
} from "./skill-categories";
import { useAddSkill, useUpdateSkill } from "./use-profile-skills";

export type LibraryRow = NonNullable<ProfileMatrix["rows"]>[number];
export type LibraryGroup = NonNullable<ProfileMatrix["groups"]>[number];
export type LibraryCategory = NonNullable<ProfileMatrix["categories"]>[number];

export function LibrarySelect({
  id,
  value,
  onChange,
  children,
  disabled,
  label,
}: {
  id?: string;
  value: string;
  onChange: (value: string) => void;
  children: ReactNode;
  disabled?: boolean;
  label?: string;
}) {
  return (
    <select
      id={id}
      value={value}
      onChange={(event) => onChange(event.target.value)}
      disabled={disabled}
      aria-label={label}
      className="h-10 min-w-0 max-w-full rounded-lg border border-input bg-background px-3 text-sm outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/50 disabled:opacity-50"
    >
      {children}
    </select>
  );
}

export function SkillEditorDialog({
  row,
  groups,
  onClose,
  disabled = false,
  initialGroup,
  returnFocus,
}: {
  row?: LibraryRow;
  groups: LibraryGroup[];
  onClose: () => void;
  disabled?: boolean;
  initialGroup?: string;
  returnFocus?: HTMLElement | null;
}) {
  const copy = useSkillCopy();
  const id = useId();
  const [name, setName] = useState(row?.display ?? "");
  const [aliases, setAliases] = useState((row?.aliases ?? []).join("\n"));
  const [category, setCategory] = useState<SkillCategory>(
    row ? skillCategoryValue(row.category) : "hard",
  );
  const [group, setGroup] = useState(
    row?.groupSource === "correction"
      ? (row.group ?? "")
      : (initialGroup ?? ""),
  );
  const add = useAddSkill();
  const update = useUpdateSkill();
  const pending = add.isPending || update.isPending;
  const error = add.error ?? update.error;
  function submit(event: FormEvent) {
    event.preventDefault();
    if (!name.trim() || pending || disabled) return;
    const body = {
      name: name.trim(),
      aliases: [
        ...new Set(
          aliases
            .split(/[,\n]/)
            .map((alias) => alias.trim())
            .filter(Boolean),
        ),
      ],
      category: category === "unspecified" ? null : category,
      group,
    };
    if (row) update.mutate({ key: row.key, ...body }, { onSuccess: onClose });
    else add.mutate(body, { onSuccess: onClose });
  }
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !pending) onClose();
      }}
    >
      <DialogContent
        overlayClassName="transition-none"
        className="min-w-0 transition-none sm:max-w-lg"
        showCloseButton={!pending}
        finalFocus={() => (returnFocus?.isConnected ? returnFocus : true)}
      >
        <DialogHeader>
          <DialogTitle>{row ? copy.edit_skill : copy.add_a_skill}</DialogTitle>
          <DialogDescription>
            {row ? copy.editDescription : copy.addDescription}
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="grid min-w-0 gap-4">
          <div className="grid gap-1.5">
            <label htmlFor={`${id}-name`} className="text-sm font-medium">
              Skill name
            </label>
            <Input
              id={`${id}-name`}
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              maxLength={200}
              autoComplete="off"
              disabled={pending || disabled}
            />
          </div>
          <div className="grid gap-1.5">
            <label htmlFor={`${id}-aliases`} className="text-sm font-medium">
              {copy.aliases}
            </label>
            <Textarea
              id={`${id}-aliases`}
              value={aliases}
              onChange={(e) => setAliases(e.target.value)}
              maxLength={10000}
              disabled={pending || disabled}
              aria-describedby={`${id}-alias-help`}
            />
            <p
              id={`${id}-alias-help`}
              className="text-xs text-muted-foreground"
            >
              {copy.aliasHelp}
            </p>
          </div>
          <div className="grid min-w-0 gap-4 sm:grid-cols-2">
            <div className="grid min-w-0 gap-1.5">
              <label htmlFor={`${id}-type`} className="text-sm font-medium">
                Skill type
              </label>
              <LibrarySelect
                id={`${id}-type`}
                value={category}
                onChange={(value) => setCategory(skillCategoryValue(value))}
                disabled={pending || disabled}
              >
                {SKILL_CATEGORIES
                  .filter(
                    (value) => !row?.inferred || value !== "unspecified",
                  )
                  .map((value) => (
                    <option key={value} value={value}>
                      {copy.skillTypes[value]}
                    </option>
                  ))}
              </LibrarySelect>
            </div>
            <div className="grid min-w-0 gap-1.5">
              <label htmlFor={`${id}-group`} className="text-sm font-medium">
                {copy.group}
              </label>
              <LibrarySelect
                id={`${id}-group`}
                value={group}
                onChange={setGroup}
                disabled={pending || disabled}
              >
                <option value="">{copy.automatic_grouping}</option>
                {groups.map((g) => (
                  <option key={g.slug} value={g.slug}>
                    {g.label}
                  </option>
                ))}
              </LibrarySelect>
            </div>
          </div>
          {error ? (
            <p role="alert" className="text-sm text-destructive">
              {error.message}
            </p>
          ) : null}
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              disabled={pending}
              onClick={onClose}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={!name.trim() || pending || disabled}
            >
              {pending ? <Spinner aria-hidden /> : null}
              {pending ? "Saving…" : row ? "Save changes" : "Add skill"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
