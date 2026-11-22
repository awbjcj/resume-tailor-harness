import type { ComponentProps } from "react";
import {
  Archive, BookOpen, ChevronDown, ChevronLeft, ChevronRight, LibraryBig, Network, SearchX,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Empty, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty";
import { ListSearch } from "@/components/ui/list-search";
import type { components } from "@/lib/api/schema";
import { formatUserDate, formatUserDateTime } from "@/lib/date-time";
import { listSearch } from "@/lib/list-search";
import { cn } from "@/lib/utils";

export type Roadmap = components["schemas"]["LearningRoadmapOut"];

const PROGRESS_VALUES = ["planned", "in_progress", "completed", "archived"] as const;
const PAGE_SIZE = 12;
const statusTone = { planned: "neutral", in_progress: "info", completed: "success", archived: "neutral" };
const chipClass = "tone-chip rounded-full px-2.5 py-0.5 text-xs font-medium data-[tone=neutral]:text-foreground";

export function RoadmapProgressSelect({ filter, ...props }: ComponentProps<"select"> & { filter?: boolean }) {
  const { t } = useTranslation();
  return (
    <div className="relative min-w-0">
      <select
        className="h-11 w-full min-w-0 appearance-none rounded-lg border border-input bg-card px-3 pe-9 text-base shadow-xs outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/25 disabled:cursor-wait disabled:opacity-60 md:text-[0.95rem] dark:bg-input/30"
        {...props}
      >
        {filter && <>
          <option value="active">{t("roadmaps.active")}</option>
          <option value="all">{t("roadmaps.all")}</option>
        </>}
        {PROGRESS_VALUES.map((value) => <option key={value} value={value}>{t(`roadmaps.${value}`)}</option>)}
      </select>
      <ChevronDown aria-hidden="true" className="pointer-events-none absolute end-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
    </div>
  );
}

export function RoadmapKind({ kind }: { kind: "skill" | "domain" }) {
  const { t } = useTranslation();
  const Icon = kind === "domain" ? Network : BookOpen;
  return (
    <span className="inline-flex items-center gap-2 text-sm font-medium text-muted-foreground">
      <span className="grid size-8 shrink-0 place-items-center rounded-md bg-primary/10 text-primary">
        <Icon aria-hidden="true" className="size-4" />
      </span>
      {t(`roadmaps.${kind}`)}
    </span>
  );
}

export function RoadmapDate({ timestamp, showTime = false }: { timestamp: string; showTime?: boolean }) {
  const { t, i18n } = useTranslation();
  const date = showTime
    ? formatUserDateTime(timestamp, i18n.resolvedLanguage, { dateStyle: "medium", timeStyle: "short" })
    : formatUserDate(timestamp, i18n.resolvedLanguage, { dateStyle: "medium" });
  return <time dateTime={timestamp}>{t("roadmaps.updated", { date })}</time>;
}

function RoadmapCard({ plan, params }: { plan: Roadmap; params: URLSearchParams }) {
  const { t } = useTranslation();
  const { suggestion, stale } = plan.envelope;
  const issue = plan.supersededById ? "supersededLabel" : !plan.available ? "unavailableLabel" : stale ? "stale" : null;
  const detailParams = new URLSearchParams(params);
  detailParams.set("plan", String(plan.id));

  return (
    <li className="flex min-w-0 flex-auto basis-full @xl/library:basis-[calc((100%-1rem)/2)] @5xl/library:basis-[calc((100%-2rem)/3)]">
      <Card className="@container/roadmap-card w-full min-w-0 gap-0 overflow-visible p-0">
        <Link
          id={`roadmap-link-${plan.id}`}
          to={{ search: detailParams.toString() }}
          state={{ fromRoadmapLibrary: true }}
          aria-labelledby={`roadmap-title-${plan.id}`}
          aria-describedby={`roadmap-status-${plan.id}`}
          className={cn(
            "group grid h-full min-w-0 scroll-mt-24 grid-cols-1 grid-rows-[auto_1fr_auto] gap-3 rounded-lg p-4 outline-none [overflow-wrap:anywhere] sm:p-5",
            "motion-safe:transition-[background-color] motion-safe:duration-150 motion-safe:ease-out-strong pointer-fine:hover:bg-accent/35 active:not-focus-visible:bg-accent",
            "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring focus-visible:transition-none",
            "@2xl/roadmap-card:grid-cols-[minmax(0,1fr)_minmax(12rem,0.36fr)] @2xl/roadmap-card:grid-rows-[auto_1fr] @2xl/roadmap-card:gap-x-6",
          )}
        >
          <div id={`roadmap-status-${plan.id}`} className="col-span-full flex flex-wrap items-center justify-between gap-2">
            <RoadmapKind kind={suggestion?.kind ?? "skill"} />
            <span className="flex min-w-0 flex-wrap items-center gap-1.5">
              <span data-tone={statusTone[plan.status]} className={chipClass}>
                {t(`roadmaps.${plan.status}`)}
              </span>
              {issue && <span data-tone={issue === "stale" ? "warning" : "neutral"} className={chipClass}>
                {t(`roadmaps.${issue}`)}
              </span>}
            </span>
          </div>
          <div className="min-w-0 space-y-1">
            <h3 id={`roadmap-title-${plan.id}`} className="font-heading text-lg leading-snug font-semibold pointer-fine:group-hover:text-primary">
              {plan.label}
            </h3>
            {suggestion?.bridge && <p className="line-clamp-2 max-w-prose text-sm leading-relaxed text-muted-foreground">{suggestion.bridge}</p>}
          </div>
          <div className="flex min-w-0 items-center justify-between gap-2 border-t pt-3 text-xs text-muted-foreground @2xl/roadmap-card:flex-col @2xl/roadmap-card:items-end @2xl/roadmap-card:border-s @2xl/roadmap-card:border-t-0 @2xl/roadmap-card:ps-4 @2xl/roadmap-card:pt-0">
            {suggestion?.generatedAt && <RoadmapDate timestamp={suggestion.generatedAt} />}
            <span aria-hidden="true" className="ms-auto flex items-center gap-1.5 text-sm font-medium text-primary">
              <span className="hidden @2xl/roadmap-card:inline">{t("roadmaps.viewRoadmap")}</span>
              <ChevronRight className="size-5 shrink-0" />
            </span>
          </div>
        </Link>
      </Card>
    </li>
  );
}

export function RoadmapLibrary({ plans }: { plans: Roadmap[] }) {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const search = params.get("q") ?? "";
  const requestedStatus = params.get("status");
  const status = requestedStatus === "all" ? "all" : PROGRESS_VALUES.find((value) => value === requestedStatus) ?? "active";
  const matches = listSearch(search);
  const visible = plans.filter(({ label, status: progress, envelope: { suggestion } }) =>
    (status === "all" || (status === "active" ? progress !== "archived" : progress === status)) &&
    matches(label, suggestion?.bridge, suggestion?.project?.title),
  );
  const pageCount = Math.max(1, Math.ceil(visible.length / PAGE_SIZE));
  const requestedPage = Number(params.get("page"));
  const page = Number.isInteger(requestedPage) ? Math.min(pageCount, Math.max(1, requestedPage)) : 1;
  const first = (page - 1) * PAGE_SIZE;
  const archivedOnly = status === "active" && !search.trim() && visible.length === 0;

  function setFilters(nextSearch: string, nextStatus: string) {
    const next = new URLSearchParams(params);
    if (nextSearch) next.set("q", nextSearch); else next.delete("q");
    if (nextStatus === "active") next.delete("status"); else next.set("status", nextStatus);
    next.delete("page");
    next.delete("plan");
    setParams(next, { replace: true });
  }

  function focusLibrary() {
    document.getElementById("roadmap-library-heading")?.focus();
  }

  function turnPage(nextPage: number) {
    const next = new URLSearchParams(params);
    if (nextPage === 1) next.delete("page"); else next.set("page", String(nextPage));
    setParams(next);
    focusLibrary();
  }

  return (
    <section aria-labelledby="roadmap-library-heading" className="@container/library flex min-w-0 flex-col gap-4">
      <Card>
        <CardContent className="flex min-w-0 flex-wrap items-end gap-4 sm:px-5">
          <div className="flex min-w-0 flex-[1_1_12rem] items-center gap-3">
            <span className="grid size-11 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary">
              <LibraryBig aria-hidden="true" className="size-5" />
            </span>
            <div className="min-w-0">
              <h2 id="roadmap-library-heading" tabIndex={-1} className="scroll-mt-24 font-heading text-base font-semibold outline-none">
                {t("roadmaps.library")}
              </h2>
              <p className="text-sm text-muted-foreground" role="status">
                {pageCount > 1
                  ? t(first + 1 === visible.length ? "roadmaps.resultLast" : "roadmaps.resultRange", {
                    first: first + 1, last: Math.min(first + PAGE_SIZE, visible.length), count: visible.length,
                  })
                  : t("roadmaps.count", { count: visible.length })}
              </p>
            </div>
          </div>
          <div className="grid min-w-0 flex-[2_1_26rem] gap-3 @xl/library:grid-cols-[minmax(0,1fr)_minmax(10rem,12rem)]">
            <div className="grid min-w-0 gap-1.5">
              <label htmlFor="roadmap-search" className="font-medium">{t("roadmaps.search")}</label>
              <ListSearch
                id="roadmap-search"
                value={search}
                placeholder={t("roadmaps.searchPlaceholder")}
                onChange={(value) => setFilters(value, status)}
                onKeyDown={(event) => { if (event.key === "Escape" && search) setFilters("", status); }}
              />
            </div>
            <label className="grid min-w-0 gap-1.5 font-medium">
              {t("roadmaps.filterStatus")}
              <RoadmapProgressSelect filter value={status} onChange={(event) => setFilters(search, event.target.value)} />
            </label>
          </div>
        </CardContent>
      </Card>

      {visible.length ? (
        <ul role="list" className="flex flex-wrap gap-4">
          {visible.slice(first, first + PAGE_SIZE).map((plan) => <RoadmapCard key={plan.id} plan={plan} params={params} />)}
        </ul>
      ) : (
        <Empty className="min-h-60 rounded-lg border bg-card shadow-card">
          <EmptyHeader>
            <EmptyMedia variant="icon" className="size-10 bg-primary/10 text-primary">
              {archivedOnly ? <Archive aria-hidden="true" /> : <SearchX aria-hidden="true" />}
            </EmptyMedia>
            <EmptyTitle className="text-base">{t(archivedOnly ? "roadmaps.archivedOnly" : "roadmaps.noMatches")}</EmptyTitle>
          </EmptyHeader>
          <Button variant="outline" size="lg" onClick={() => {
            setFilters("", archivedOnly ? "archived" : "active");
            focusLibrary();
          }}>
            {t(archivedOnly ? "roadmaps.viewArchived" : "roadmaps.resetFilters")}
          </Button>
        </Empty>
      )}

      {pageCount > 1 && (
        <nav aria-label={t("roadmaps.pagination")} className="flex flex-wrap items-center justify-end gap-2">
          <span className="me-2 text-sm tabular-nums text-muted-foreground">{t("roadmaps.pageOf", { page, total: pageCount })}</span>
          <Button variant="outline" size="icon-lg" aria-label={t("roadmaps.previousPage")} disabled={page === 1} onClick={() => turnPage(page - 1)}>
            <ChevronLeft aria-hidden="true" />
          </Button>
          <Button variant="outline" size="icon-lg" aria-label={t("roadmaps.nextPage")} disabled={page === pageCount} onClick={() => turnPage(page + 1)}>
            <ChevronRight aria-hidden="true" />
          </Button>
        </nav>
      )}
    </section>
  );
}
