import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader } from "@/components/PageHeader";

/** Shared recovery state. Never present a failed request as an empty result. */
export function QueryFeedback({ error, onRetry, loadingLabel = "Loading settings" }: {
  error?: Error | null;
  onRetry?: () => unknown;
  loadingLabel?: string;
}) {
  if (error) return (
    <Alert variant="destructive">
      <AlertTitle>Could not load this section</AlertTitle>
      <AlertDescription>
        <p className="whitespace-pre-wrap [overflow-wrap:anywhere]">{error.message}</p>
        {onRetry && <Button variant="outline" className="mt-2 w-fit" onClick={() => void onRetry()}>Retry</Button>}
      </AlertDescription>
    </Alert>
  );
  return (
    <div role="status" aria-label={loadingLabel} aria-busy="true" className="flex flex-col gap-5">
      <span className="sr-only">{loadingLabel}</span>
      <Skeleton className="h-5 w-1/3" />
      <Skeleton className="h-11 w-full" />
      <Skeleton className="h-11 w-full" />
      <Skeleton className="h-28 w-full" />
    </div>
  );
}

export function PageFeedback({ title, error, onRetry }: {
  title: string;
  error?: Error | null;
  onRetry?: () => unknown;
}) {
  return <div className="flex min-w-0 flex-col gap-6">
    <PageHeader title={title} />
    <QueryFeedback error={error} onRetry={onRetry} loadingLabel={title} />
  </div>;
}
