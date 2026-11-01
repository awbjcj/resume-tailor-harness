import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export type GuidedWorkspaceTone = "coach" | "interview" | "scout" | "career-lab";

export function GuidedWorkspaceHeader({
  tone,
  icon,
  eyebrow,
  title,
  description,
  meta,
  actions,
  className,
}: {
  tone: GuidedWorkspaceTone;
  icon: ReactNode;
  eyebrow: string;
  title: ReactNode;
  description: ReactNode;
  meta?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <header
      data-tone={tone}
      className={cn(
        "guided-workspace-hero relative overflow-hidden rounded-xl px-4 py-3 shadow-card ring-1 ring-foreground/10 sm:px-5 sm:py-3.5",
        className,
      )}
    >
      <div className="relative flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 flex-[1_1_24rem] items-center gap-3">
          <div className="hidden size-9 shrink-0 items-center justify-center rounded-lg border border-current/10 bg-background/75 text-(--workspace-tone) shadow-sm sm:flex [&_svg]:size-4" aria-hidden="true">
            {icon}
          </div>
          <div className="min-w-0 [overflow-wrap:anywhere]">
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <h1 className="text-xl leading-tight font-semibold tracking-[-0.025em] sm:text-2xl">{title}</h1>
              <p className="text-[11px] font-semibold tracking-[0.14em] text-(--workspace-tone) uppercase">{eyebrow}</p>
            </div>
            <div className="mt-0.5 max-w-[76ch] text-sm leading-5 text-muted-foreground">{description}</div>
            {meta ? <div className="mt-2 flex flex-wrap items-center gap-1.5">{meta}</div> : null}
          </div>
        </div>
        {actions ? <div className="flex min-w-0 max-w-full flex-wrap items-center gap-2 [&>[data-slot=button]]:h-auto [&>[data-slot=button]]:min-h-10 [&>[data-slot=button]]:max-w-full [&>[data-slot=button]]:whitespace-normal">{actions}</div> : null}
      </div>
    </header>
  );
}
