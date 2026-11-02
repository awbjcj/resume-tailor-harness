import { useId, type ReactNode } from "react";

import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import type { ProfileMatrix } from "@/features/settings/use-matrix";
import { useSkillCopy } from "@/i18n/skill-copy";
import {
  SKILL_CATEGORIES,
  skillCategoryValue,
  type SkillCategory,
} from "./skill-categories";

export type LibraryRow = NonNullable<ProfileMatrix["rows"]>[number];
export type LibraryGroup = NonNullable<ProfileMatrix["groups"]>[number];
export type LibraryCategory = NonNullable<ProfileMatrix["categories"]>[number];

export type SkillDraft = {
  name: string;
  aliases: string;
  category: SkillCategory;
  group: string;
};

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

export function SkillEditorFields({
  value,
  onChange,
  groups,
  inferred = false,
  disabled,
}: {
  value: SkillDraft;
  onChange: (value: SkillDraft) => void;
  groups: LibraryGroup[];
  inferred?: boolean;
  disabled: boolean;
}) {
  const copy = useSkillCopy();
  const id = useId();
  return (
    <>
      <div className="grid gap-1.5">
        <label htmlFor={`${id}-name`} className="text-sm font-medium">
          Skill name
        </label>
        <Input
          id={`${id}-name`}
          value={value.name}
          onChange={(event) => onChange({ ...value, name: event.target.value })}
          required
          maxLength={200}
          autoComplete="off"
          disabled={disabled}
        />
      </div>
      <div className="grid gap-1.5">
        <label htmlFor={`${id}-aliases`} className="text-sm font-medium">
          {copy.aliases}
        </label>
        <Textarea
          id={`${id}-aliases`}
          value={value.aliases}
          onChange={(event) => onChange({ ...value, aliases: event.target.value })}
          maxLength={10000}
          disabled={disabled}
          aria-describedby={`${id}-alias-help`}
        />
        <p id={`${id}-alias-help`} className="text-xs text-muted-foreground">
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
            value={value.category}
            onChange={(category) =>
              onChange({ ...value, category: skillCategoryValue(category) })
            }
            disabled={disabled}
          >
            {SKILL_CATEGORIES.filter(
              (category) => !inferred || category !== "unspecified",
            ).map((category) => (
              <option key={category} value={category}>
                {copy.skillTypes[category]}
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
            value={value.group}
            onChange={(group) => onChange({ ...value, group })}
            disabled={disabled}
          >
            <option value="">{copy.automatic_grouping}</option>
            {groups.map((group) => (
              <option key={group.slug} value={group.slug}>
                {group.label}
              </option>
            ))}
          </LibrarySelect>
        </div>
      </div>
    </>
  );
}
