import type { ReactNode } from "react";

import { PageHeader } from "@/components/PageHeader";
import { cn } from "@/lib/utils";

export type GuidedWorkspaceTone = "coach" | "interview" | "scout" | "career-lab";

export function GuidedWorkspaceHeader({
  tone,
  icon,
  title,
  meta,
  actions,
  className,
}: {
  tone: GuidedWorkspaceTone;
  icon: ReactNode;
  title: ReactNode;
  meta?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <PageHeader
      className={cn("guided-workspace-header", className)}
      title={<span className="flex items-center gap-3"><span data-tone={tone} aria-hidden="true" className="guided-workspace-icon shrink-0 [&_svg]:size-6">{icon}</span><span>{title}</span></span>}
      meta={meta}
      actions={actions}
    />
  );
}
