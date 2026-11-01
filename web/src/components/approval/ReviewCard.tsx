import { useId, type ReactNode, type Ref } from "react";
import { ClipboardCheck } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardFooter, CardHeader } from "@/components/ui/card";
import { cn } from "@/lib/utils";

/** A consistent frame for proposed changes and their explicit human decision. */
export function ReviewCard({ title, description, status, tone = "info", busy, children, footer, className, focusRef }: {
  title: ReactNode;
  description?: ReactNode;
  status: ReactNode;
  tone?: "info" | "success" | "warning" | "neutral";
  busy?: boolean;
  children: ReactNode;
  footer?: ReactNode;
  className?: string;
  focusRef?: Ref<HTMLDivElement>;
}) {
  const titleId = useId();
  return (
    <Card ref={focusRef} tabIndex={-1} role="group" aria-labelledby={titleId} aria-busy={busy || undefined}
      className={cn("@container/review min-w-0 gap-0 rounded-xl border py-0 shadow-none ring-0 outline-none focus-visible:ring-2 focus-visible:ring-ring", className)}>
      <CardHeader className="gap-3 p-4 sm:p-5">
        <div className="flex min-w-0 items-start gap-3">
          <span className="flex size-9 shrink-0 items-center justify-center rounded-lg border bg-muted/40 text-muted-foreground">
            <ClipboardCheck className="size-4" aria-hidden="true" />
          </span>
          <div className="min-w-0 flex-1 space-y-2">
            <Badge variant="outline" data-tone={tone === "neutral" ? undefined : tone}
              className={cn("h-auto max-w-full whitespace-normal text-xs", tone !== "neutral" && "tone-chip")}>
              {status}
            </Badge>
            <h3 id={titleId} className="text-base font-semibold leading-snug [overflow-wrap:anywhere]">{title}</h3>
          </div>
        </div>
        {description ? <p className="text-sm leading-relaxed text-muted-foreground [overflow-wrap:anywhere]">{description}</p> : null}
      </CardHeader>
      <CardContent className="min-w-0 border-t px-0">{children}</CardContent>
      {footer ? <CardFooter className="min-w-0 flex-col items-stretch gap-3 bg-muted/25 p-4 sm:p-5">{footer}</CardFooter> : null}
    </Card>
  );
}
