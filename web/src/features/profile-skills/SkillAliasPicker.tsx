import { useId, useState } from "react";

import { Button } from "@/components/ui/button";
import { ListSearch } from "@/components/ui/list-search";
import { ListSection } from "@/components/ui/list-section";
import { Spinner } from "@/components/ui/spinner";
import { useSkillCopy } from "@/i18n/skill-copy";
import { listSearch } from "@/lib/list-search";
import { SKILL_CATEGORIES, skillCategoryValue } from "./skill-categories";
import { useProfileSkills } from "./use-profile-skills";

export function SkillAliasPicker({
  disabled,
  onSelect,
}: {
  disabled: boolean;
  onSelect: (skillId: string) => void;
}) {
  const copy = useSkillCopy();
  const aliasId = useId();
  const [search, setSearch] = useState("");
  const skills = useProfileSkills();
  const query = search.trim();
  const matches = listSearch(query);
  const shown = (skills.data ?? [])
    .filter((skill) => matches(skill.name, ...(skill.aliases ?? [])))
    .sort((left, right) => left.name.localeCompare(right.name));
  const sections = SKILL_CATEGORIES.map((category) => ({
    category,
    rows: shown.filter((skill) => skillCategoryValue(skill.category) === category),
  })).filter(({ rows }) => rows.length);

  return (
    <div className="grid min-w-0 gap-3">
      <ListSearch
        value={search}
        onChange={setSearch}
        placeholder={copy.search_skills_and_aliases_placeholder}
        aria-label={copy.search_skills_and_aliases}
        disabled={disabled}
      />
      {skills.isPending ? (
        <p role="status" className="flex items-center gap-2 text-muted-foreground">
          <Spinner aria-hidden />
          {copy.loadingSkills}
        </p>
      ) : skills.isError ? (
        <div role="alert" className="text-destructive">
          <p>{copy.couldNotLoadSkills}</p>
          <Button variant="link" onClick={() => void skills.refetch()}>
            {copy.tryAgain}
          </Button>
        </div>
      ) : shown.length ? (
        <section aria-label={copy.your_skill_library} className="max-h-[min(18rem,45svh)] space-y-2 overflow-y-auto overscroll-contain p-0.5">
          {sections.map(({ category, rows }) => (
            <ListSection key={category} label={copy.skillTypes[category]} count={rows.length} query={query} defaultOpen={sections.length === 1 || shown.length <= 12} className="rounded-md border bg-muted/25">
              <ul className="divide-y border-t bg-card">
                {rows.map((skill) => (
                  <li key={skill.id}>
                    <Button
                      type="button"
                      variant="ghost"
                      className="h-auto min-h-11 w-full justify-start whitespace-normal text-left"
                      aria-label={skill.name}
                      aria-describedby={query && skill.aliases?.length ? `${aliasId}-${skill.id}` : undefined}
                      disabled={disabled}
                      onClick={() => onSelect(skill.id)}
                    >
                      <span className="min-w-0 [overflow-wrap:anywhere]">
                        {skill.name}
                        {query && skill.aliases?.length ? (
                          <span id={`${aliasId}-${skill.id}`} className="block text-xs font-normal text-muted-foreground">{skill.aliases.join(", ")}</span>
                        ) : null}
                      </span>
                    </Button>
                  </li>
                ))}
              </ul>
            </ListSection>
          ))}
        </section>
      ) : (
        <p role="status" className="text-sm text-muted-foreground">
          {skills.data?.length ? copy.noMatches : copy.noAliasTargets}
        </p>
      )}
    </div>
  );
}
