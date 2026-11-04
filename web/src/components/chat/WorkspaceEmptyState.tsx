import type { ComponentType, ReactNode } from "react";
import { ArrowRight } from "lucide-react";

import { Button } from "@/components/ui/button";

export function WorkspaceEmptyState({
  icon: Icon,
  title,
  description,
  actionLabel,
  onAction,
  busy = false,
  actionIcon,
}: {
  icon: ComponentType<{ className?: string; "aria-hidden"?: "true" }>;
  title: string;
  description: string;
  actionLabel: string;
  onAction: () => void;
  busy?: boolean;
  actionIcon?: ReactNode;
}) {
  return (
    <div className="mx-auto flex w-full max-w-xl flex-1 flex-col items-center justify-center px-5 py-12 text-center sm:px-8">
      <div className="flex size-12 items-center justify-center rounded-xl border bg-background text-primary shadow-sm">
        <Icon className="size-5" aria-hidden="true" />
      </div>
      <h2 className="mt-4 text-xl font-semibold tracking-[-0.02em]">{title}</h2>
      <p className="mt-1.5 max-w-xl text-sm leading-6 text-muted-foreground">{description}</p>
      <Button className="mt-5" disabled={busy} onClick={onAction}>
        {actionIcon}
        {actionLabel}
        {!actionIcon ? <ArrowRight aria-hidden="true" /> : null}
      </Button>
    </div>
  );
}
