import { useState } from "react";
import { Undo2 } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { ListSearch } from "@/components/ui/list-search";
import { ListSection } from "@/components/ui/list-section";
import type { SuppressedSkill } from "@/features/settings/use-matrix";
import { useSkillCopy } from "@/i18n/skill-copy";
import { localizeSkillLabel } from "@/i18n/skill-labels";
import { listSearch } from "@/lib/list-search";

export function RemovedSkillList({ skills, disabled, onRestore }: {
  skills: SuppressedSkill[];
  disabled: boolean;
  onRestore: (token: string) => void;
}) {
  const copy = useSkillCopy();
  const { i18n, t } = useTranslation();
  const [search, setSearch] = useState("");
  const matches = listSearch(search);
  const entries = skills.filter((skill) => matches(
    skill.display, skill.token, skill.reason,
    skill.reason ? localizeSkillLabel(skill.reason, i18n.resolvedLanguage) : undefined,
  ));
  const groups = [
    { label: copy.removedManually, rows: entries.filter((skill) => !skill.reason) },
    { label: copy.removedByCleanup, rows: entries.filter((skill) => !!skill.reason) },
  ];
  return (
    <ListSection label={copy.removedSkills} count={skills.length} className="rounded-lg border">
      <div className="space-y-2 border-t p-3">
        <p className="text-xs text-muted-foreground">{copy.restoreHelp}</p>
        <ListSearch value={search} onChange={setSearch} aria-label={copy.searchRemoved} placeholder={copy.searchRemoved} />
        <p role="status" className="text-sm text-muted-foreground">
          {entries.length ? t("longLists.results", { shown: entries.length, total: skills.length }) : t("longLists.noMatches")}
        </p>
        {groups.map(({ label, rows }) => rows.length > 0 ? (
          <ListSection key={label} level={4} label={label} count={rows.length} query={search.trim()} defaultOpen={skills.length <= 12} className="rounded-md border bg-card">
            <ul className="divide-y border-t">
              {rows.map((skill) => (
                <li key={skill.token} className="flex min-w-0 flex-wrap items-center justify-between gap-2 px-3 py-2">
                  <div className="min-w-0 flex-1 [overflow-wrap:anywhere]">
                    <p className="text-sm font-medium">{skill.display}</p>
                    {skill.reason ? <p className="text-xs text-muted-foreground">{localizeSkillLabel(skill.reason, i18n.resolvedLanguage)}</p> : null}
                  </div>
                  <Button type="button" variant="outline" size="sm" disabled={disabled} aria-label={copy.restoreSkill(skill.display)} onClick={() => onRestore(skill.token)}>
                    <Undo2 aria-hidden />
                    {copy.restore}
                  </Button>
                </li>
              ))}
            </ul>
          </ListSection>
        ) : null)}
      </div>
    </ListSection>
  );
}
