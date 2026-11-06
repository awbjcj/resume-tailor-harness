import { isProvisionalSkill } from "./aggregate";
import { useId, useState } from "react";
import { ChevronRightIcon, ExternalLinkIcon } from "lucide-react";
import { useTranslation } from "react-i18next";
import "@/i18n/long-list-copy";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";
import {
  sortSkillsWithin,
  targetId,
  UNASSIGNED_ID,
  type SkillRow,
  type SuggestionState,
  type SuggestionTarget,
  type DomainRow,
  type CategoryRow,
} from "./aggregate";

const INITIAL_DOMAINS = 8;
const INITIAL_SKILLS = 8;

const STATUS_LABEL: Record<SuggestionState, string> = {
  none: "Not generated",
  ready: "Ready",
  stale: "Stale",
  queued: "Queued",
  researching: "Researching",
  failed: "Failed",
  cancelled: "Cancelled",
  not_found: "Unavailable",
};

function StatusBadge({ state }: { state: SuggestionState }) {
  if (state === "none") return null;
  const variant = state === "failed" || state === "not_found" ? "destructive" : "outline";
  return (
    <Badge variant={variant} className={cn(state === "ready" && "border-ready text-ready")}>
      {STATUS_LABEL[state]}
    </Badge>
  );
}

// A dense, scannable stat line reused by both category and domain headers. Each
// figure is only rendered when it carries signal (score/gaps/adjacent hidden at
// zero) so a clean domain doesn't read as a wall of "0 · 0 · 0".
function StatLine({
  score,
  skillCount,
  gapCount,
  adjacentCount,
}: {
  score: number;
  skillCount: number;
  gapCount: number;
  adjacentCount: number;
}) {
  const { t } = useTranslation();
  const parts = [
    t("longLists.outline.skillCount", { count: skillCount }),
    score > 0 ? t("longLists.outline.score", { score }) : null,
    gapCount > 0 ? t("longLists.outline.gapCount", { count: gapCount }) : null,
    adjacentCount > 0 ? t("longLists.outline.adjacent", { count: adjacentCount }) : null,
  ].filter((part) => part !== null);
  return (
    <span className="inline-flex min-w-0 flex-wrap gap-x-1 font-mono text-xs tabular-nums text-muted-foreground [overflow-wrap:anywhere]">
      {parts.map((part, index) => (
        <span key={part} className="max-w-full">{index > 0 ? "· " : null}{part}</span>
      ))}
    </span>
  );
}

function ScoreBar({ score, maximum }: { score: number; maximum: number }) {
  return (
    <span aria-hidden className="h-1.5 min-w-0 flex-[1_1_4rem] overflow-hidden rounded-full bg-muted">
      <span
        className="block h-full rounded-full bg-primary"
        style={{ width: `${Math.min(100, (score / maximum) * 100)}%` }}
      />
    </span>
  );
}

export function RankedList({
  domainRows,
  categoryRows,
  query = "",
  stateOf,
  selected,
  onToggleSelect,
  onOpenSkill,
}: {
  domainRows: DomainRow[];
  categoryRows: CategoryRow[];
  query?: string;
  stateOf: (kind: "skill" | "domain", key: string) => SuggestionState;
  selected: Set<string>;
  onToggleSelect: (target: SuggestionTarget) => void;
  onOpenSkill: (skill: SkillRow) => void;
}) {
  const { t } = useTranslation();
  // Categories expose the taxonomy and domains open on demand.
  const statsId = useId();
  const [collapsedCategories, setCollapsedCategories] = useState<Set<string>>(new Set());
  const [expandedDomains, setExpandedDomains] = useState<Set<string>>(new Set());
  const [searchClosed, setSearchClosed] = useState<{ query: string; keys: Set<string> }>();
  const [domainLimits, setDomainLimits] = useState<Record<string, number>>({});
  const [skillLimits, setSkillLimits] = useState<Record<string, number>>({});
  if (searchClosed && searchClosed.query !== query) setSearchClosed(undefined);
  const maximum = Math.max(1, ...domainRows.map((domain) => domain.score));
  const searchCollapsed = (key: string) => searchClosed?.query === query && searchClosed.keys.has(key);
  function setSearchOpen(key: string, open: boolean) {
    setSearchClosed((current) => {
      const keys = new Set(current?.query === query ? current.keys : undefined);
      if (open) keys.delete(key);
      else keys.add(key);
      return { query, keys };
    });
  }

  const setCategoryOpen = (slug: string, open: boolean) =>
    setCollapsedCategories((current) => {
      const next = new Set(current);
      if (open) next.delete(slug);
      else next.add(slug);
      return next;
    });
  const setDomainOpen = (id: string, open: boolean) =>
    setExpandedDomains((current) => {
      const next = new Set(current);
      if (open) next.add(id);
      else next.delete(id);
      return next;
    });

  return (
    <section aria-labelledby="ranked-domains-title" className="@container/outline min-w-0 border-y bg-card">
      <header className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-b px-4 py-4 sm:px-5">
        <h2 id="ranked-domains-title" className="text-sm font-semibold">
          Skill outline
        </h2>
        <span className="font-mono text-xs text-muted-foreground">
          {t("longLists.outline.categoryCount", { count: categoryRows.length })} · {t("longLists.outline.domainCount", { count: domainRows.length })}
        </span>
      </header>

      <div className="divide-y">
        {categoryRows.map((category) => {
          const categoryKey = `category:${category.slug}`;
          const categoryStatsId = `${statsId}-${category.slug}`;
          const categoryOpen = query ? !searchCollapsed(categoryKey) : !collapsedCategories.has(category.slug);
          const domainLimit = domainLimits[category.slug] ?? INITIAL_DOMAINS;
          const visibleDomains = category.domains.slice(0, domainLimit);
          return (
            <Collapsible
              key={category.slug}
              open={categoryOpen}
              onOpenChange={(open) => query ? setSearchOpen(categoryKey, open) : setCategoryOpen(category.slug, open)}
            >
              <CollapsibleTrigger
                render={<Button variant="ghost" size="lg" />}
                aria-label={`${categoryOpen ? "Collapse" : "Expand"} ${category.label}`}
                aria-describedby={categoryStatsId}
                className="grid h-auto min-h-11 w-full grid-cols-[auto_minmax(0,1fr)] items-center gap-x-3 gap-y-1 rounded-none bg-muted/40 px-4 py-3 text-left whitespace-normal transition-none hover:bg-muted/60 active:bg-muted/75 @lg/outline:grid-cols-[auto_minmax(0,1fr)_auto] sm:px-5"
              >
                <ChevronRightIcon
                  aria-hidden
                  className={cn("text-muted-foreground", categoryOpen && "rotate-90")}
                />
                <span className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
                  <span className="min-w-0 text-xs font-semibold uppercase tracking-wide [overflow-wrap:anywhere]">{category.label}</span>
                  <Badge variant={category.kind === "hard" ? "default" : "outline"}>
                    {category.kind}
                  </Badge>
                </span>
                <span id={categoryStatsId} className="col-start-2 min-w-0 @lg/outline:col-start-3 @lg/outline:max-w-48 @lg/outline:text-right">
                  <StatLine
                    score={category.score}
                    skillCount={category.skillCount}
                    gapCount={category.gapCount}
                    adjacentCount={category.adjacentCount}
                  />
                </span>
              </CollapsibleTrigger>

              <CollapsibleContent>
                <div className="divide-y border-t">
                  {visibleDomains.map((domain) => {
                    const domainKey = `domain:${domain.id}`;
                    const open = query ? !searchCollapsed(domainKey) : expandedDomains.has(domain.id);
                    const domainTarget = { kind: "domain" as const, key: domain.id, label: domain.label };
                    const orderedSkills = sortSkillsWithin(domain.skills, (key) =>
                      stateOf("skill", key),
                    );
                    const skillLimit = skillLimits[domain.id] ?? INITIAL_SKILLS;
                    return (
                      <Collapsible
                        key={domain.id}
                        open={open}
                        onOpenChange={(next) => query ? setSearchOpen(domainKey, next) : setDomainOpen(domain.id, next)}
                      >
                        <div className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-2 px-4 py-3 @sm/outline:gap-3 sm:px-5 sm:pl-8">
                          <Checkbox
                            aria-label={`Select ${domain.label} domain`}
                            checked={selected.has(targetId(domainTarget))}
                            onCheckedChange={() => onToggleSelect(domainTarget)}
                            disabled={domain.id === UNASSIGNED_ID}
                          />
                          <div className="min-w-0">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="min-w-0 text-sm font-semibold [overflow-wrap:anywhere]">{domain.label}</span>
                              <StatusBadge state={stateOf("domain", domain.id)} />
                            </div>
                            <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1">
                              <ScoreBar score={domain.score} maximum={maximum} />
                              <StatLine
                                score={domain.score}
                                skillCount={domain.skillCount}
                                gapCount={domain.gapCount}
                                adjacentCount={domain.adjacentCount}
                              />
                            </div>
                          </div>
                          <CollapsibleTrigger
                            render={<Button variant="ghost" size="icon-lg" className="transition-none active:bg-muted/75" />}
                            aria-label={`${open ? "Collapse" : "Expand"} ${domain.label}`}
                          >
                            <ChevronRightIcon
                              aria-hidden
                              className={cn(open && "rotate-90")}
                            />
                          </CollapsibleTrigger>
                        </div>

                        <CollapsibleContent>
                          <ul className="border-t bg-muted/20 px-4 sm:px-5 sm:pl-8">
                            {orderedSkills.slice(0, skillLimit).map((skill) => {
                              const skillTarget = {
                                kind: "skill" as const,
                                key: skill.key,
                                label: skill.skill,
                              };
                              return (
                                <li
                                  key={skill.key}
                                  className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-2 border-b py-2.5 last:border-b-0 @sm/outline:gap-3"
                                >
                                  <Checkbox
                                    aria-label={`Select ${skill.skill}`}
                                    checked={selected.has(targetId(skillTarget))}
                                    onCheckedChange={() => onToggleSelect(skillTarget)}
                                  />
                                  <div className="min-w-0">
                                    <div className="flex flex-wrap items-center gap-2">
                                      <span className="min-w-0 text-sm font-medium [overflow-wrap:anywhere]">{skill.skill}</span>
                                      <Badge
                                        variant={
                                          skill.coverage === "covered"
                                            ? "secondary"
                                            : skill.coverage === "gap"
                                              ? "destructive"
                                              : "outline"
                                        }
                                        className={cn(
                                          skill.coverage === "adjacent" &&
                                            "border-adjacent text-adjacent",
                                        )}
                                      >
                                        {skill.coverage === "covered"
                                          ? "Covered"
                                          : skill.coverage === "adjacent"
                                            ? "Adjacent"
                                            : "Gap"}
                                      </Badge>
                                      <StatusBadge state={stateOf("skill", skill.key)} />
                                    </div>
                                    <p className="mt-1 text-xs text-muted-foreground">
                                      {t("longLists.outline.jobCount", { count: skill.jobCount })} · {t("longLists.outline.score", { score: skill.score })}
                                    </p>
                                    {(isProvisionalSkill(skill) || skill.groupingStatus) && (
                                      <p className="mt-1 text-xs text-muted-foreground">
                                        {isProvisionalSkill(skill)
                                          ? "Provisional category placement; the specific domain still needs confirmation."
                                          : `Grouping ${skill.groupingStatus?.state}: ${skill.groupingStatus?.reason}`}
                                      </p>
                                    )}
                                  </div>
                                  <Button
                                    variant="ghost"
                                    size="icon-lg"
                                    className="gap-1.5 @sm/outline:w-auto @sm/outline:px-3"
                                    aria-label={`Open ${skill.skill} details`}
                                    onClick={() => onOpenSkill(skill)}
                                  >
                                    <span className="hidden @sm/outline:inline">Details</span>
                                    <ExternalLinkIcon aria-hidden />
                                  </Button>
                                </li>
                              );
                            })}
                          </ul>
                          {orderedSkills.length > skillLimit && (
                            <div className="border-t px-5 py-2 pl-6 sm:pl-8">
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() =>
                                  setSkillLimits((limits) => ({
                                    ...limits,
                                    [domain.id]: skillLimit + INITIAL_SKILLS,
                                  }))
                                }
                              >
                                Show {Math.min(INITIAL_SKILLS, orderedSkills.length - skillLimit)} more skills
                              </Button>
                            </div>
                          )}
                        </CollapsibleContent>
                      </Collapsible>
                    );
                  })}
                  {category.domains.length > domainLimit && (
                    <div className="px-5 py-2 pl-6 sm:pl-8">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() =>
                          setDomainLimits((limits) => ({
                            ...limits,
                            [category.slug]: domainLimit + INITIAL_DOMAINS,
                          }))
                        }
                      >
                        Show {Math.min(INITIAL_DOMAINS, category.domains.length - domainLimit)} more domains
                      </Button>
                    </div>
                  )}
                </div>
              </CollapsibleContent>
            </Collapsible>
          );
        })}
      </div>
    </section>
  );
}
