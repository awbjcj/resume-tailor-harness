import { Undo2Icon } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ListSearch } from "@/components/ui/list-search";
import { ListSection } from "@/components/ui/list-section";

import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverHeader,
  PopoverTitle,
  PopoverTrigger,
} from "@/components/ui/popover";
import type { components } from "@/lib/api/schema";
import { listSearch } from "@/lib/list-search";
import { localizeDisplayValue } from "@/i18n/dynamic-labels";
import { useSkillCopy } from "@/i18n/skill-copy";
import { useRestoreSkills } from "./use-taxonomy";

type RetiredSkill = components["schemas"]["RetiredSkillOut"];

/**
 * Retired tokens are removed from the backlog entirely, so they have to stay
 * visible somewhere: a wrong call would otherwise be both invisible and
 * permanent. Restoring returns one to the next regroup.
 */
export function RetiredSkills({ skills }: { skills: RetiredSkill[] }) {
  const restore = useRestoreSkills();
  const { t, i18n } = useTranslation();
  const copy = useSkillCopy();
  const [query, setQuery] = useState("");
  const matches = listSearch(query);
  const groups = new Map<string, RetiredSkill[]>();
  const matching = skills.filter((skill) =>
    matches(skill.key, skill.reason, localizeDisplayValue(skill.reason, i18n.resolvedLanguage)),
  );
  for (const skill of matching) {
    const members = groups.get(skill.reason) ?? [];
    members.push(skill);
    groups.set(skill.reason, members);
  }
  if (skills.length === 0) return null;

  return (
    <Popover>
      <PopoverTrigger
        render={
          <Button variant="ghost" size="xs" className="text-muted-foreground" />
        }
      >
        {`${skills.length} discarded non-skills`}
      </PopoverTrigger>
      <PopoverContent align="end" className="max-h-(--available-height) w-80 max-w-[min(var(--available-width),calc(100vw-2rem))] gap-0 overflow-y-auto overscroll-contain p-0">
        <PopoverHeader className="gap-1 p-4 pb-2">
          <PopoverTitle>Discarded non-skills</PopoverTitle>
          <p className="text-xs text-muted-foreground">
            These entries are excluded from skill demand and regrouping. Restore
            any valid entries.
          </p>
          <ListSearch
            aria-label="Search discarded entries"
            placeholder="Search entries…"
            value={query}
            onChange={setQuery}
          />
        </PopoverHeader>
        <div className="space-y-2 px-3">
          {[...groups].map(([reason, rows]) => (
            <ListSection key={reason} label={localizeDisplayValue(reason, i18n.resolvedLanguage)} count={rows.length} query={query.trim()} defaultOpen={skills.length <= 12} className="rounded-md border bg-muted/20">
              <ul className="divide-y border-t">
                {rows.map((skill) => (
                  <li key={skill.key} className="flex items-center justify-between gap-2 px-3 py-2">
                    <span className="min-w-0 text-sm [overflow-wrap:anywhere]">{skill.key}</span>
                    <Button variant="outline" size="sm" aria-label={copy.restoreSkill(skill.key)} disabled={restore.isPending} onClick={() => restore.mutate([skill.key])}>
                      <Undo2Icon data-icon="inline-start" />
                      Restore
                    </Button>
                  </li>
                ))}
              </ul>
            </ListSection>
          ))}
        </div>
        <p role="status" className="px-4 pt-2 text-xs text-muted-foreground">
          {matching.length ? t("longLists.results", { shown: matching.length, total: skills.length }) : t("longLists.noMatches")}
        </p>
        <div className="p-3">
          <Button
            variant="outline"
            size="sm"
            className="w-full"
            disabled={restore.isPending}
            onClick={() => restore.mutate(skills.map((skill) => skill.key))}
          >
            Restore all {skills.length}
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
