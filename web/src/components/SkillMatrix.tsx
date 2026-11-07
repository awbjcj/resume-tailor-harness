// Full skill set, grouped Must-have / Nice-to-have. Two independent channels:
//   required  -> which group (must vs nice)
//   covered   -> chip fill (solid = you have it, dashed outline = gap)
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { ListSearch } from "@/components/ui/list-search";
import { ListSection } from "@/components/ui/list-section";
import type { SkillTag } from "@/lib/filters/types";
import { listSearch } from "@/lib/list-search";
import { AddJobSkillButton } from "@/features/profile-skills/AddJobSkillButton";

function Chip({
  tag,
  active,
}: {
  tag: SkillTag;
  active: boolean;
}) {
  return (
    <span
      className="skill-chip pointer-coarse:min-h-11"
      data-covered={tag.covered}
      data-active={active}
      title={
        tag.covered ? "Covered by your profile" : "Profile gap: not yet in your profile"
      }
    >
      <span aria-hidden className="shrink-0 text-[0.7em] opacity-80">
        {tag.covered ? "●" : "○"}
      </span>
      <span className="min-w-0 [overflow-wrap:anywhere]">{tag.name}</span>
      {!tag.covered && (
        <span className="-mr-1 inline-flex shrink-0 items-center justify-center">
          <AddJobSkillButton skillName={tag.name} />
        </span>
      )}
    </span>
  );
}

function Group({
  label,
  tags,
  activeSkills,
  query,
  defaultOpen,
}: {
  label: string;
  tags: SkillTag[];
  activeSkills: Set<string>;
  query: string;
  defaultOpen: boolean;
}) {
  if (tags.length === 0) return null;
  return (
    <ListSection label={label} count={tags.length} level={4} query={query} defaultOpen={defaultOpen} className="rounded-lg border bg-muted/20">
      <ul className="flex flex-wrap gap-1.5 border-t px-3 py-2.5">
        {tags.map((t) => (
          <li key={t.name} className="min-w-0"><Chip tag={t} active={activeSkills.has(t.name.toLowerCase())} /></li>
        ))}
      </ul>
    </ListSection>
  );
}

export function SkillMatrix({
  skills,
  activeSkills = new Set(),
}: {
  skills: SkillTag[];
  activeSkills?: Set<string>;
}) {
  const { t } = useTranslation();
  const [search, setSearch] = useState("");
  const mustLabel = t("longLists.mustHave");
  const niceLabel = t("longLists.niceToHave");
  const matches = listSearch(search);
  const shown = skills.filter((skill) => matches(
    skill.name,
    skill.required ? mustLabel : niceLabel,
    t(skill.covered ? "longLists.coveredSkill" : "longLists.skillGap"),
  ));
  const must = shown.filter((skill) => skill.required);
  const nice = shown.filter((skill) => !skill.required);
  const covered = skills.filter((s) => s.covered).length;

  if (skills.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">No skills extracted for this job.</p>
    );
  }

  return (
    <div className="min-w-0 space-y-2">
      {skills.length > 12 || search ? (
        <ListSearch value={search} onChange={setSearch} aria-label={t("longLists.searchJobSkills")} placeholder={t("longLists.searchJobSkills")} />
      ) : null}
      <p role="status" className="text-sm text-muted-foreground empty:sr-only">
        {search.trim() ? shown.length ? t("longLists.results", { shown: shown.length, total: skills.length }) : t("longLists.noMatches") : null}
      </p>
      <Group label={mustLabel} tags={must} activeSkills={activeSkills} query={search.trim()} defaultOpen />
      <Group label={niceLabel} tags={nice} activeSkills={activeSkills} query={search.trim()} defaultOpen={skills.length <= 12 || must.length === 0} />
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t pt-3 text-sm text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <span aria-hidden className="text-primary">●</span> you have
        </span>
        <span className="flex items-center gap-1.5">
          <span aria-hidden>○</span> gap
        </span>
        <span className="ml-auto font-medium tabular-nums">
          {covered}/{skills.length} covered
        </span>
      </div>
    </div>
  );
}
