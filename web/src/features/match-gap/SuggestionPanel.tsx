import { useId, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import "@/i18n/roadmap-copy";
import {
  BookOpen,
  ChevronDown,
  ExternalLink,
  GitFork,
  Hammer,
  Lightbulb,
  Star,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { SuggestionEnvelope } from "./use-suggestion";

const sectionClass = "min-w-0 flex-auto basis-full rounded-lg border @xl/advice:basis-[calc((100%-1rem)/2)] @5xl/advice:basis-[calc((100%-2rem)/3)]";
const sectionHeadingClass = "flex items-center gap-2 font-heading text-sm font-semibold";
const cardHeadingClass = cn(sectionHeadingClass, "border-b px-4 py-3");
const linkRowClass = "flex min-w-0 items-center justify-between gap-x-2 @max-[18rem]/advice:flex-col @max-[18rem]/advice:items-start";

function AdviceLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a
      className="inline-flex min-h-11 min-w-0 max-w-full items-center gap-2 rounded-sm py-2 font-medium text-primary underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-ring"
      href={href}
      target="_blank"
      rel="noreferrer"
    >
      <span className="min-w-0">{children}</span>
      <ExternalLink aria-hidden="true" className="size-3 shrink-0" />
    </a>
  );
}

export function SuggestionPanel({
  envelope,
  isLoading,
  isError = false,
  onRetry = () => {},
  onGenerate,
  generating,
  canGenerate = true,
}: {
  envelope: SuggestionEnvelope | undefined;
  isLoading: boolean;
  isError?: boolean;
  onRetry?: () => void;
  onGenerate: () => void;
  generating: boolean;
  canGenerate?: boolean;
}) {
  const { t, i18n } = useTranslation();
  const sectionId = useId();
  if (isLoading) {
    return (
      <div role="status" aria-busy="true" aria-label="Loading gap-closing advice" className="space-y-3 motion-reduce:[&_[data-slot=skeleton]]:animate-none">
        <Skeleton className="h-4 w-2/5" />
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-16 w-full" />
      </div>
    );
  }

  if (isError) {
    return (
      <div role="alert" className="border-l-2 border-destructive pl-3 text-sm">
        <p className="font-medium">Couldn't load saved advice.</p>
        <p className="mt-1 text-muted-foreground">Try again without closing this panel.</p>
        <Button className="mt-3 min-h-11" size="sm" variant="outline" onClick={onRetry}>
          Retry
        </Button>
      </div>
    );
  }

  const suggestion = envelope?.suggestion;
  if (!suggestion) {
    if (!canGenerate) return <p className="text-sm text-muted-foreground">{t("roadmaps.noSavedAdvice")}</p>;
    return (
      <div className="border-l-2 border-primary/45 pl-4">
        <p className="text-sm font-medium">No learning advice yet</p>
        <p className="mt-1 text-sm leading-6 text-muted-foreground">
          Generate learning advice that may include repositories, resources, or a project idea.
        </p>
        <Button className="mt-3 h-auto min-h-11 max-w-full whitespace-normal" size="sm" disabled={generating} onClick={onGenerate}>
          <Lightbulb aria-hidden="true" data-icon="inline-start" />
          {generating ? "Researching…" : "How to close this gap"}
        </Button>
      </div>
    );
  }

  return (
    <div className="@container/advice min-w-0 space-y-5 text-sm [overflow-wrap:anywhere]">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <h3 className="font-heading text-base font-semibold">How to close this gap</h3>
          {canGenerate && envelope.stale && <span data-tone="warning" className="tone-chip rounded-full px-2.5 py-0.5 text-xs font-medium">{t("roadmaps.stale")}</span>}
        </div>
        {canGenerate && <Button size="sm" variant="outline" className="h-auto min-h-11 max-w-full whitespace-normal" disabled={generating} onClick={onGenerate}>
          {generating ? "Researching…" : "Regenerate"}
        </Button>}
      </div>

      {suggestion.bridge && (
        <div className="rounded-lg border bg-accent/30 px-4 py-3.5">
          <h4 className={sectionHeadingClass}>
            <Lightbulb aria-hidden="true" className="size-4 shrink-0 text-primary" />
            Build on what you know
          </h4>
          <p className="mt-1.5 max-w-prose leading-6 text-muted-foreground">{suggestion.bridge}</p>
        </div>
      )}

      <div className="flex flex-wrap items-stretch gap-4 empty:hidden">
        {suggestion.project && (
          <section aria-labelledby={`${sectionId}-project`} className={cn(sectionClass, "bg-muted/25")}>
            <h4 id={`${sectionId}-project`} className={cardHeadingClass}>
              <Hammer aria-hidden="true" className="size-4 shrink-0 text-primary" />
              Project idea
            </h4>
            <div className="px-4 py-3">
              <p className="font-semibold">{suggestion.project.title}</p>
              <p className="mt-1 max-w-prose leading-6 text-muted-foreground">{suggestion.project.summary}</p>
              {suggestion.project.skillsDemonstrated.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {suggestion.project.skillsDemonstrated.map((skill) => (
                    <Badge key={skill} variant="outline" className="h-auto min-h-5 max-w-full whitespace-normal">
                      {skill}
                    </Badge>
                  ))}
                </div>
              )}
            </div>
          </section>
        )}

        {suggestion.repos.length > 0 && (
          <section aria-labelledby={`${sectionId}-repositories`} className={sectionClass}>
            <h4 id={`${sectionId}-repositories`} className={cardHeadingClass}>
              <GitFork aria-hidden="true" className="size-4 shrink-0 text-primary" />
              Repositories to learn from
            </h4>
            <ul role="list" className="divide-y px-4">
              {suggestion.repos.map((repository) => (
                <li key={repository.url} className="pb-2.5">
                  <div className={linkRowClass}>
                    <AdviceLink href={repository.url}>{repository.name}</AdviceLink>
                    {typeof repository.stars === "number" && (
                      <span role="img" aria-label={t("roadmaps.stars", { count: repository.stars })} className="flex shrink-0 items-center gap-1 text-xs tabular-nums text-muted-foreground">
                        <Star aria-hidden="true" className="size-3" />
                        {repository.stars.toLocaleString(i18n.resolvedLanguage)}
                      </span>
                    )}
                  </div>
                  {repository.description && <p className="max-w-prose text-muted-foreground">{repository.description}</p>}
                  {repository.why && <p className="mt-1 max-w-prose text-sm leading-relaxed text-muted-foreground">{repository.why}</p>}
                </li>
              ))}
            </ul>
          </section>
        )}

        {suggestion.resources.length > 0 && (
          <section aria-labelledby={`${sectionId}-resources`} className={sectionClass}>
            <h4 id={`${sectionId}-resources`} className={cardHeadingClass}>
              <BookOpen aria-hidden="true" className="size-4 shrink-0 text-primary" />
              Learning resources
            </h4>
            <ul role="list" className="divide-y px-4">
              {suggestion.resources.map((resource) => (
                <li key={resource.url} className={linkRowClass}>
                  <AdviceLink href={resource.url}>{resource.title}</AdviceLink>
                  <Badge variant="secondary" className="h-auto min-h-5 max-w-full whitespace-normal @max-[18rem]/advice:mb-2.5">
                    {t(`roadmaps.resource_${resource.kind}`)}
                  </Badge>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>

      {suggestion.citations.length > 0 && (
        <details className="group rounded-lg border">
          <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-2 rounded-lg px-4 py-2 font-medium hover:bg-muted/50 focus-visible:outline-2 focus-visible:outline-ring [&::-webkit-details-marker]:hidden">
            <span>Sources</span>
            <ChevronDown aria-hidden="true" className="size-4 shrink-0 text-muted-foreground group-open:rotate-180" />
          </summary>
          <ul role="list" className="divide-y border-t px-4">
            {suggestion.citations.map((url) => (
              <li key={url}>
                <AdviceLink href={url}>{url}</AdviceLink>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
