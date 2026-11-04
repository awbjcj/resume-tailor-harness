import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export function PageHeader({
  title,
  meta,
  actions,
  className,
}: {
  title: ReactNode;
  meta?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <header className={cn("flex min-w-0 flex-wrap items-center justify-between gap-4 border-b pb-5", className)}>
      <div className="min-w-0 flex-1 basis-60 [overflow-wrap:anywhere]">
        <h1 className="text-balance font-heading text-2xl font-semibold leading-tight tracking-[-0.03em] text-foreground sm:text-3xl">
          {title}
        </h1>
        {meta ? <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">{meta}</div> : null}
      </div>
      {actions ? <div className="flex min-w-0 max-w-full flex-wrap items-center gap-2 [&>[data-slot=button]]:h-auto [&>[data-slot=button]]:min-h-10 [&>[data-slot=button]]:max-w-full [&>[data-slot=button]]:whitespace-normal">{actions}</div> : null}
    </header>
  );
}
