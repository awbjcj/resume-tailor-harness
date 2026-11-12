import "@/i18n/roadmap-copy";
import { useEffect, useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, BookOpen, Info } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { PageHeader } from "@/components/PageHeader";
import { QueryFeedback } from "@/components/QueryFeedback";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { buttonVariants } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia } from "@/components/ui/empty";
import { api, unwrap } from "@/lib/api/client";

import { RoadmapDate, RoadmapKind, RoadmapLibrary, RoadmapProgressSelect, type Roadmap } from "./RoadmapLibrary";
import { SuggestionPanel } from "./SuggestionPanel";
import { useGenerateSuggestion } from "./use-suggestion";

const ROADMAPS_QUERY_KEY = ["learning-roadmaps"];

function ExploreSkillGaps({ primary = false }: { primary?: boolean }) {
  const { t } = useTranslation();
  return (
    <Link to="/match-gap" data-slot="button" className={buttonVariants({ variant: primary ? "default" : "outline", size: "lg", className: "py-2.5" })}>
      {t("roadmaps.back")}
      <ArrowRight aria-hidden="true" data-icon="inline-end" />
    </Link>
  );
}

export function LearningRoadmapsPage() {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const pageStart = useRef<HTMLDivElement>(null);
  const detailHeading = useRef<HTMLHeadingElement>(null);
  const openedFrom = useRef<number | null>(null);
  const progressToRestore = useRef<HTMLSelectElement | null>(null);
  const query = useQuery({ queryKey: ROADMAPS_QUERY_KEY, queryFn: () => unwrap(api.GET("/api/learning-roadmaps")) });
  const { generate, generating } = useGenerateSuggestion();
  const update = useMutation({
    mutationFn: ({ id, status }: { id: number; status: Roadmap["status"] }) => unwrap(api.PATCH("/api/learning-roadmaps/{suggestion_id}", {
      params: { path: { suggestion_id: id } }, body: { status },
    })),
    onSuccess: async (_, { id, status }) => {
      queryClient.setQueryData<Roadmap[]>(ROADMAPS_QUERY_KEY, (plans) => plans?.map((plan) => plan.id === id ? { ...plan, status } : plan));
      await queryClient.invalidateQueries({ queryKey: ROADMAPS_QUERY_KEY });
      toast.success(t("roadmaps.saved"));
    },
  });

  const planId = params.get("plan");
  const selected = query.data?.find((plan) => String(plan.id) === planId);
  const selectedId = selected?.id;
  const suggestion = selected?.envelope.suggestion;
  const libraryParams = new URLSearchParams(params);
  libraryParams.delete("plan");
  const currentParams = new URLSearchParams(libraryParams);
  if (selected?.supersededById) currentParams.set("plan", String(selected.supersededById));
  const updatingSelection = update.isPending && update.variables?.id === selectedId;
  const updateFailed = update.isError && update.variables?.id === selectedId;

  useEffect(() => {
    if (selectedId !== undefined) {
      openedFrom.current ??= selectedId;
      pageStart.current?.scrollIntoView?.({ block: "start" });
      detailHeading.current?.focus({ preventScroll: true });
    } else if (openedFrom.current !== null) {
      const opener = document.getElementById(`roadmap-link-${openedFrom.current}`);
      (opener ?? document.getElementById("roadmap-library-heading"))?.focus();
      openedFrom.current = null;
    }
  }, [selectedId]);

  useEffect(() => {
    if (update.isPending) return;
    const control = progressToRestore.current;
    progressToRestore.current = null;
    // Disabling a focused native select drops focus in Chromium. Restore it
    // while the control is mounted and focus is still on the document body.
    if (control?.isConnected && document.activeElement === document.body) {
      control.focus({ preventScroll: true });
    }
  }, [update.isPending]);

  return (
    <div ref={pageStart} className="flex min-w-0 scroll-mt-[calc(var(--app-chrome-height,3.5rem)+1rem)] flex-col gap-6">
      <PageHeader
        title={t("roadmaps.title")}
        description={!selected && t("roadmaps.description")}
        actions={selected ? (
          <Link
            to={{ search: libraryParams.toString() }}
            replace
            data-slot="button"
            className={buttonVariants({ variant: "outline", size: "lg", className: "py-2.5" })}
            onClick={(event) => {
              if (location.state?.fromRoadmapLibrary && event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey) {
                event.preventDefault();
                void navigate(-1);
              }
            }}
          >
            <ArrowLeft aria-hidden="true" data-icon="inline-start" />
            {t("roadmaps.backToList")}
          </Link>
        ) : query.data?.length ? <ExploreSkillGaps /> : undefined}
      />

      {!query.data ? (
        <Card className="[&_[data-slot=button]]:min-h-11 motion-reduce:[&_[data-slot=skeleton]]:animate-none">
          <div className="px-4 sm:px-6">
            <QueryFeedback
              loadingLabel={t("roadmaps.loading")}
              error={query.isError ? new Error(t("roadmaps.error")) : null}
              onRetry={() => query.refetch()}
            />
          </div>
        </Card>
      ) : selected ? (
        <section aria-labelledby="roadmap-detail-heading" className="@container/detail min-w-0 [overflow-wrap:anywhere] [&_:is(a,button,select,summary)]:scroll-mt-24">
          <Card className="gap-0 p-0">
            <header className="flex min-w-0 flex-col gap-5 border-b bg-muted/30 p-4 sm:p-6 @2xl/detail:flex-row @2xl/detail:items-end @2xl/detail:justify-between">
              <div className="min-w-0 space-y-2">
                <RoadmapKind kind={suggestion?.kind ?? "skill"} />
                <h2 ref={detailHeading} id="roadmap-detail-heading" tabIndex={-1} className="font-heading text-2xl leading-tight font-semibold tracking-tight outline-none sm:text-3xl">
                  {selected.label}
                </h2>
                {suggestion?.generatedAt && <p className="text-sm text-muted-foreground"><RoadmapDate timestamp={suggestion.generatedAt} showTime /></p>}
              </div>
              <div className="grid w-full min-w-0 gap-1.5 sm:max-w-64 @2xl/detail:shrink-0">
                <div className="flex flex-wrap items-baseline justify-between gap-x-2">
                  <label htmlFor="roadmap-progress" className="font-medium">{t("roadmaps.status")}</label>
                  <span role="status" className="text-xs text-muted-foreground">{updatingSelection ? t("roadmaps.saving") : null}</span>
                </div>
                <RoadmapProgressSelect
                  id="roadmap-progress"
                  value={updatingSelection ? update.variables?.status : selected.status}
                  disabled={update.isPending}
                  aria-describedby={updateFailed ? "roadmap-progress-error" : undefined}
                  onChange={(event) => {
                    if (document.activeElement === event.currentTarget) progressToRestore.current = event.currentTarget;
                    update.mutate({ id: selected.id, status: event.target.value as Roadmap["status"] });
                  }}
                />
                {updateFailed && <p id="roadmap-progress-error" role="alert" className="text-sm text-destructive">{t("roadmaps.saveError")}</p>}
              </div>
            </header>

            <div className="space-y-5 p-4 sm:p-6">
              {!selected.available && (
                <Alert className="tone-panel px-3 py-3" data-tone="info" role="note">
                  <Info aria-hidden="true" className="tone-accent" />
                  <AlertDescription>
                    <div className="space-y-1">
                      <p>{t(selected.supersededById ? "roadmaps.superseded" : "roadmaps.unavailable")}</p>
                      {selected.supersededById && <Link
                        to={{ search: currentParams.toString() }}
                        replace
                        state={location.state}
                        className="inline-flex min-h-11 items-center rounded-sm font-medium text-primary focus-visible:outline-2 focus-visible:outline-ring"
                      >
                        {t("roadmaps.openCurrent")}
                      </Link>}
                    </div>
                  </AlertDescription>
                </Alert>
              )}
              <SuggestionPanel
                key={selected.id}
                envelope={selected.envelope}
                isLoading={false}
                generating={generating}
                canGenerate={selected.available && Boolean(suggestion)}
                onGenerate={() => { if (suggestion) void generate(suggestion.kind, suggestion.key, selected.id); }}
              />
            </div>
          </Card>
        </section>
      ) : (
        <>
          {planId !== null && <Alert><Info aria-hidden="true" /><AlertDescription>{t("roadmaps.missing")}</AlertDescription></Alert>}
          {update.isError && <Alert variant="destructive"><AlertDescription>{t("roadmaps.saveError")}</AlertDescription></Alert>}
          {query.data.length ? <RoadmapLibrary plans={query.data} /> : (
            <Empty className="min-h-72 rounded-lg border bg-card shadow-card sm:py-14">
              <EmptyHeader>
                <EmptyMedia variant="icon" className="size-12 bg-primary/10 text-primary">
                  <BookOpen aria-hidden="true" className="size-5" />
                </EmptyMedia>
                <h2 className="font-heading text-xl font-semibold">{t("roadmaps.empty")}</h2>
                <EmptyDescription>{t("roadmaps.emptyBody")}</EmptyDescription>
              </EmptyHeader>
              <ExploreSkillGaps primary />
            </Empty>
          )}
        </>
      )}
    </div>
  );
}
