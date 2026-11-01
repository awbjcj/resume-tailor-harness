import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Spinner } from "@/components/ui/spinner";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useMatrix } from "@/features/settings/use-matrix";
import { useSkillCopy } from "@/i18n/skill-copy";
import { localizeSkillContainer } from "@/i18n/skill-labels";
import { skillCategoryValue } from "./skill-categories";
import { SkillAliasPicker } from "./SkillAliasPicker";
import {
  SkillEditorFields,
  type LibraryGroup,
  type LibraryRow,
  type SkillDraft,
} from "./SkillEditorFields";
import { useAddSkill, useAddSkillAlias, useUpdateSkill } from "./use-profile-skills";

export function SkillEditorDialog({
  row,
  groups,
  onClose,
  disabled = false,
  initialGroup,
  returnFocus,
  suggestedSkill,
}: {
  row?: LibraryRow;
  groups?: LibraryGroup[];
  onClose: () => void;
  disabled?: boolean;
  initialGroup?: string;
  returnFocus?: HTMLElement | null;
  suggestedSkill?: string;
}) {
  const copy = useSkillCopy();
  const { i18n } = useTranslation();
  const [mode, setMode] = useState<"new" | "alias">("new");
  const [draft, setDraft] = useState<SkillDraft>(() => ({
    name: row?.display ?? suggestedSkill ?? "",
    aliases: (row?.aliases ?? []).join("\n"),
    category: row ? skillCategoryValue(row.category) : "hard",
    group:
      row?.groupSource === "correction"
        ? (row.group ?? "")
        : (initialGroup ?? ""),
  }));
  const matrix = useMatrix(groups === undefined);
  const groupOptions =
    groups ??
    (matrix.data?.groups ?? []).map((group) =>
      localizeSkillContainer(group, i18n.resolvedLanguage),
    );
  const loadingGroups = groups === undefined && matrix.isPending;
  const groupError = groups === undefined && matrix.isError;
  const add = useAddSkill();
  const update = useUpdateSkill();
  const alias = useAddSkillAlias();
  const pending = add.isPending || update.isPending || alias.isPending;
  const blocked = disabled || pending || loadingGroups || groupError;
  const error = mode === "alias" ? alias.error : (add.error ?? update.error);
  const fromJob = !row && !!suggestedSkill;

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!draft.name.trim() || blocked) return;
    const previousName =
      fromJob &&
      draft.name.trim().toLocaleLowerCase() !== suggestedSkill.trim().toLocaleLowerCase()
        ? [suggestedSkill.trim()]
        : [];
    const body = {
      name: draft.name.trim(),
      aliases: [
        ...new Set([
          ...draft.aliases.split(/[,\n]/).map((name) => name.trim()).filter(Boolean),
          ...previousName,
        ]),
      ],
      category: draft.category === "unspecified" ? null : draft.category,
      group: draft.group,
    };
    if (row) update.mutate({ key: row.key, ...body }, { onSuccess: onClose });
    else add.mutate(body, { onSuccess: onClose });
  }

  const editorForm = loadingGroups ? (
    <p role="status" className="flex items-center gap-2 py-4 text-muted-foreground">
      <Spinner aria-hidden />
      {copy.loading_skill_matrix}
    </p>
  ) : groupError ? (
    <div role="alert" className="py-4 text-destructive">
      <p>{copy.couldn_t_load_the_skill_matrix}</p>
      <Button variant="link" onClick={() => void matrix.refetch()}>
        {copy.tryAgain}
      </Button>
    </div>
  ) : (
    <form onSubmit={submit} className="grid min-w-0 gap-4">
      <SkillEditorFields
        value={draft}
        onChange={setDraft}
        groups={groupOptions}
        inferred={row?.inferred}
        disabled={blocked}
      />
      {error ? (
        <p role="alert" className="text-sm text-destructive">{error.message}</p>
      ) : null}
      <DialogFooter>
        <Button type="button" variant="outline" disabled={pending} onClick={onClose}>
          {copy.cancel}
        </Button>
        <Button type="submit" disabled={!draft.name.trim() || blocked}>
          {pending ? <Spinner aria-hidden /> : null}
          {pending ? copy.saving : row ? copy.save : copy.addSkill}
        </Button>
      </DialogFooter>
    </form>
  );

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !pending) onClose();
      }}
    >
      <DialogContent
        overlayClassName="transition-none"
        className="min-w-0 transition-none [overflow-wrap:anywhere] sm:max-w-lg"
        showCloseButton={!pending}
        finalFocus={() => (returnFocus?.isConnected ? returnFocus : true)}
        onClick={(event) => event.stopPropagation()}
        onKeyDown={(event) => {
          if (event.key === "ArrowLeft" || event.key === "ArrowRight")
            event.stopPropagation();
        }}
      >
        <DialogHeader className="pr-6">
          <DialogTitle>{row ? copy.edit_skill : copy.add_a_skill}</DialogTitle>
          <DialogDescription>
            {row
              ? copy.editDescription
              : fromJob
                ? mode === "alias"
                  ? copy.addAliasDescription(suggestedSkill)
                  : copy.addFromJobDescription(suggestedSkill)
                : copy.addDescription}
          </DialogDescription>
        </DialogHeader>
        {fromJob ? (
          <Tabs
            value={mode}
            onValueChange={(value) => {
              if (!pending && (value === "new" || value === "alias")) setMode(value);
            }}
          >
            <TabsList className="w-full" aria-label={copy.addSkillMethod}>
              <TabsTrigger value="new" disabled={pending}>{copy.newSkill}</TabsTrigger>
              <TabsTrigger value="alias" disabled={pending}>{copy.existingSkill}</TabsTrigger>
            </TabsList>
            <TabsContent value="new" className="pt-2">
              {editorForm}
            </TabsContent>
            <TabsContent value="alias" className="space-y-4 pt-2">
              <SkillAliasPicker
                disabled={disabled || pending}
                onSelect={(skillId) => {
                  if (!disabled && !pending)
                    alias.mutate({ skillId, alias: suggestedSkill }, { onSuccess: onClose });
                }}
              />
              {pending ? (
                <p role="status" className="flex items-center gap-2 text-muted-foreground">
                  <Spinner aria-hidden />{copy.saving}
                </p>
              ) : null}
              {error ? (
                <p role="alert" className="text-sm text-destructive">{error.message}</p>
              ) : null}
              <DialogFooter>
                <Button type="button" variant="outline" disabled={pending} onClick={onClose}>
                  {copy.cancel}
                </Button>
              </DialogFooter>
            </TabsContent>
          </Tabs>
        ) : editorForm}
      </DialogContent>
    </Dialog>
  );
}
