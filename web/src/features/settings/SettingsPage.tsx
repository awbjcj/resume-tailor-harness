import { useId, type ReactNode } from "react";

import { PageHeader } from "@/components/PageHeader";
import { QueryFeedback } from "@/components/QueryFeedback";
import { cn } from "@/lib/utils";

/** Consistent title, purpose, and recovery for each settings destination. */
export function SettingsPage({ title, description, actions, loading, error, onRetry, children }: {
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
  loading?: boolean;
  error?: Error | null;
  onRetry?: () => unknown;
  children?: ReactNode;
}) {
  return (
    <div className="@container/settings flex min-w-0 flex-col gap-7">
      <PageHeader title={title} description={description} actions={actions} />
      {error && <QueryFeedback error={error} onRetry={onRetry} />}
      {loading ? <QueryFeedback /> : children}
    </div>
  );
}

/** A decision group, without another card inside the settings surface. */
export function SettingsSection({ title, description, children, className }: {
  title: string;
  description?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  const id = useId();
  return (
    <section aria-labelledby={id} className={cn("flex min-w-0 flex-col gap-4 border-b pb-7 last:border-b-0 last:pb-0", className)}>
      <div className="flex flex-col gap-1.5">
        <h2 id={id} className="text-base font-semibold leading-snug">{title}</h2>
        {description && <div className="max-w-prose text-sm leading-relaxed text-muted-foreground">{description}</div>}
      </div>
      {children}
    </section>
  );
}
