import { useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams, Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { ListSearch } from "@/components/ui/list-search";
import { EmptyState } from "@/components/EmptyState";
import { QueryFeedback } from "@/components/QueryFeedback";
import { Badge } from "@/components/ui/badge";
import { api, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { SuggestionPanel } from "./SuggestionPanel";
import { useGenerateSuggestion } from "./use-suggestion";
import "@/i18n/roadmap-copy";

type Roadmap = components["schemas"]["LearningRoadmapOut"];
const PROGRESS_VALUES = ["planned", "in_progress", "completed", "archived"] as const;
const selectClass = "h-11 w-full min-w-0 rounded-lg border border-input bg-background px-3 text-sm focus-visible:outline-2 focus-visible:outline-ring disabled:cursor-not-allowed disabled:opacity-50 dark:bg-input/30";

function focusRoadmapDetail() {
  document.getElementById("roadmap-detail-heading")?.focus({
    preventScroll: window.innerWidth >= 1024,
  });
}

export function LearningRoadmapsPage() {
  const { t, i18n } = useTranslation();
  const [params, setParams] = useSearchParams();
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["learning-roadmaps"], queryFn: () => unwrap(api.GET("/api/learning-roadmaps")) });
  const { generate, generating } = useGenerateSuggestion();
  const update = useMutation({
    mutationFn: ({ id, status }: { id: number; status: Roadmap["status"] }) => unwrap(api.PATCH("/api/learning-roadmaps/{suggestion_id}", { params: { path: { suggestion_id: id } }, body: { status } })),
    onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: ["learning-roadmaps"] }); toast.success(t("roadmaps.saved")); },
    onError: () => toast.error(t("roadmaps.saveError")),
  });
  const changeParam = (key: string, value: string) => setParams((current) => { const next = new URLSearchParams(current); if (value) next.set(key, value); else next.delete(key); return next; }, { replace: key !== "plan" });
  const search = params.get("q") ?? "";
  const status = params.get("status") ?? "active";
  const plans = query.data ?? [];
  const selected = plans.find((plan) => String(plan.id) === params.get("plan"));
  const selectedId = selected?.id;
  // Move keyboard users to the opened plan; on narrow screens also bring it
  // into view instead of leaving it below a potentially long library list.
  useEffect(() => {
    if (selectedId === undefined) return;
    focusRoadmapDetail();
  }, [selectedId]);
  const visible = plans.filter((plan) => (status === "all" || (status === "active" ? plan.status !== "archived" : plan.status === status)) && `${plan.label} ${plan.envelope.suggestion?.bridge ?? ""}`.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()));
  return <div className="flex min-w-0 flex-col gap-6">
    <PageHeader title={t("roadmaps.title")} description={t("roadmaps.description")}
      actions={<Button variant="outline" nativeButton={false} render={<Link to="/match-gap" />}>{t("roadmaps.back")}</Button>} />
    {query.isLoading || query.isError ? (
      <QueryFeedback loadingLabel={t("roadmaps.loading")}
        error={query.isError ? new Error(t("roadmaps.error")) : null}
        onRetry={() => query.refetch()} />
    ) : plans.length === 0 ? (
      <EmptyState title={t("roadmaps.empty")} body={t("roadmaps.emptyBody")} />
    ) : <>
      <div className="grid min-w-0 items-end gap-3 rounded-lg border bg-card p-4 sm:grid-cols-[minmax(0,1fr)_minmax(10rem,14rem)]">
        <div className="grid min-w-0 gap-1.5 text-sm font-medium">
          <label htmlFor="roadmap-search">{t("roadmaps.search")}</label>
          <ListSearch id="roadmap-search" value={search} placeholder={t("roadmaps.search")}
            onChange={(value) => changeParam("q", value)}
            onKeyDown={(event) => { if (event.key === "Escape") changeParam("q", ""); }} />
        </div>
        <label className="grid min-w-0 gap-1.5 text-sm font-medium">{t("roadmaps.filterStatus")}
          <select className={selectClass} value={status} onChange={(event) => changeParam("status", event.target.value)}>
            <option value="active">{t("roadmaps.active")}</option><option value="all">{t("roadmaps.all")}</option>
            {PROGRESS_VALUES.map((value) => <option key={value} value={value}>{t(`roadmaps.${value}`)}</option>)}
          </select>
        </label>
      </div>
      <p className="text-sm text-muted-foreground" role="status">{t("roadmaps.count", { count: visible.length })}</p>
      <div className="grid min-w-0 items-start gap-6 lg:grid-cols-[minmax(16rem,1fr)_minmax(0,2fr)]">
        <nav id="roadmap-list" tabIndex={-1} aria-label={t("roadmaps.title")} className="min-w-0 rounded-lg border bg-card">
          {visible.length === 0 ? <div className="space-y-3 p-5 text-sm"><p>{t("roadmaps.noMatches")}</p><Button variant="outline" onClick={() => setParams((current) => { const next = new URLSearchParams(current); next.delete("q"); next.delete("status"); return next; }, { replace: true })}>{t("roadmaps.resetFilters")}</Button></div> : <ul className="divide-y">{visible.map((plan) => <li key={plan.id} className="first:rounded-t-lg last:rounded-b-lg">
            <Link to={`?${new URLSearchParams({ ...Object.fromEntries(params), plan: String(plan.id) })}`} aria-current={selected?.id === plan.id ? "page" : undefined}
              onClick={() => { if (selectedId === plan.id) focusRoadmapDetail(); }}
              className="block min-w-0 space-y-2 rounded-[inherit] p-4 hover:bg-accent focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring aria-[current=page]:bg-accent aria-[current=page]:text-accent-foreground [overflow-wrap:anywhere]">
              <span className="block font-semibold">{plan.label}</span>
              <span className="flex flex-wrap gap-2"><Badge variant="outline">{t(`roadmaps.${plan.envelope.suggestion?.kind ?? "skill"}`)}</Badge><Badge variant="secondary">{t(`roadmaps.${plan.status}`)}</Badge>{plan.envelope.stale && <Badge variant="outline">{t("roadmaps.stale")}</Badge>}</span>
            </Link>
          </li>)}</ul>}
        </nav>
        <section className="min-w-0 rounded-lg border bg-card p-4 sm:p-6 [overflow-wrap:anywhere]" aria-label={selected?.label ?? t("roadmaps.title")}>
          {selected ? <>
            <Button variant="ghost" size="sm" className="mb-4 lg:hidden" onClick={() => document.getElementById("roadmap-list")?.focus()}>{t("roadmaps.backToList")}</Button>
            <h2 id="roadmap-detail-heading" tabIndex={-1} className="text-xl font-semibold outline-none">{selected.label}</h2>
            <p className="mt-2 text-sm text-muted-foreground">{t("roadmaps.updated", { date: new Date(selected.envelope.suggestion!.generatedAt).toLocaleString(i18n.resolvedLanguage) })}</p>
            <label className="my-5 grid max-w-64 gap-1.5 text-sm font-medium">{t("roadmaps.status")}<select className={selectClass} value={selected.status} disabled={update.isPending}
              onChange={(event) => update.mutate({ id: selected.id, status: event.target.value as Roadmap["status"] })}>
              {PROGRESS_VALUES.map((value) => <option key={value} value={value}>{t(`roadmaps.${value}`)}</option>)}
            </select></label>
            {update.isError && <p role="alert" className="mb-4 text-sm text-destructive">{t("roadmaps.saveError")}</p>}
            {!selected.available && <div className="mb-5 space-y-2 text-sm text-muted-foreground">
              <p>{t(selected.supersededById ? "roadmaps.superseded" : "roadmaps.unavailable")}</p>
              {selected.supersededById && <Link className="text-primary underline underline-offset-2" to={`?${new URLSearchParams({ ...Object.fromEntries(params), status: "all", plan: String(selected.supersededById) })}`}>{t("roadmaps.openCurrent")}</Link>}
            </div>}
            <SuggestionPanel envelope={selected.envelope} isLoading={false} generating={generating} canGenerate={selected.available}
              onGenerate={() => { const suggestion = selected.envelope.suggestion!; void generate(suggestion.kind, suggestion.key, selected.id); }} />
          </> : <p className="py-8 text-sm text-muted-foreground">{t(params.has("plan") ? "roadmaps.missing" : "roadmaps.choose")}</p>}
        </section>
      </div>
    </>}
  </div>;
}
