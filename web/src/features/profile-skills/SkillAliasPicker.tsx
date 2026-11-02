import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { useSkillCopy } from "@/i18n/skill-copy";
import { skillCategoryValue } from "./skill-categories";
import { useProfileSkills } from "./use-profile-skills";

export function SkillAliasPicker({
  disabled,
  onSelect,
}: {
  disabled: boolean;
  onSelect: (skillId: string) => void;
}) {
  const copy = useSkillCopy();
  const [search, setSearch] = useState("");
  const skills = useProfileSkills();
  const query = search.trim().toLocaleLowerCase();
  const shown = (skills.data ?? [])
    .filter((skill) =>
      [skill.name, ...(skill.aliases ?? [])].some((name) =>
        name.toLocaleLowerCase().includes(query),
      ),
    )
    .sort((left, right) => left.name.localeCompare(right.name));

  return (
    <div className="grid min-w-0 gap-3">
      <Input
        value={search}
        onChange={(event) => setSearch(event.target.value)}
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
        <ul aria-label={copy.your_skill_library} className="max-h-60 space-y-1 overflow-y-auto">
          {shown.map((skill) => (
            <li key={skill.id}>
              <Button
                type="button"
                variant="outline"
                className="h-auto min-h-10 w-full justify-between gap-3 whitespace-normal text-left"
                disabled={disabled}
                onClick={() => onSelect(skill.id)}
              >
                <span className="min-w-0 [overflow-wrap:anywhere]">{skill.name}</span>
                <span className="shrink-0 text-xs text-muted-foreground">
                  {copy.skillTypes[skillCategoryValue(skill.category)]}
                </span>
              </Button>
            </li>
          ))}
        </ul>
      ) : (
        <p role="status" className="text-sm text-muted-foreground">
          {skills.data?.length ? copy.noMatches : copy.noAliasTargets}
        </p>
      )}
    </div>
  );
}
