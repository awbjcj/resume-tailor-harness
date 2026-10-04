import { X } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { CareerLabContext } from "./use-career-lab";

export function CareerLabContextSummary({ context, onChange, disabled = false }: { context: CareerLabContext; onChange: (context: CareerLabContext) => void; disabled?: boolean }) {
  const items = [
    ...(context.profileSnapshot ? [{ label: "Current profile", clear: () => onChange({ ...context, profileSnapshot: undefined }) }] : []),
    ...(context.jobId ? [{ label: `Job #${context.jobId}`, clear: () => onChange({ ...context, jobId: undefined, resumeVersionId: undefined }) }] : []),
    ...(context.resumeVersionId ? [{ label: `Resume #${context.resumeVersionId}`, clear: () => onChange({ ...context, resumeVersionId: undefined }) }] : []),
    ...(context.offerApplicationIds?.length ? [{ label: `${context.offerApplicationIds.length} offer references`, clear: () => onChange({ ...context, offerApplicationIds: [] }) }] : []),
    ...(context.artifact ? [{ label: "Selected draft", clear: () => onChange({ ...context, artifact: undefined }) }] : []),
  ];
  return <div aria-label="Context for next message" className="space-y-2">
    <p className="text-xs font-medium text-muted-foreground">Context for next message</p>
    <div className="flex flex-wrap gap-1.5">
      {items.length ? items.map((item) => <Button key={item.label} variant="outline" size="sm" disabled={disabled} onClick={item.clear} aria-label={`Remove ${item.label}`} className="h-7 rounded-full text-xs">{item.label}<X className="size-3" aria-hidden="true" /></Button>) : <p className="text-xs text-muted-foreground">Conversation only. Add references in the context panel.</p>}
    </div>
  </div>;
}
