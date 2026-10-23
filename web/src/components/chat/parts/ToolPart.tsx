import { Check, ChevronDown, Loader2, Wrench, X } from "lucide-react";

import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import type { ChatPart } from "@/lib/chat/events";

type ToolChatPart = Extract<ChatPart, { kind: "tool" }>;

const TOOL_LABELS: Record<string, string> = {
  web_search: "Web search",
  web_fetch: "Read web page",
  list_corpus_documents: "List source documents",
  read_document: "Read source document",
  list_github_sources: "List GitHub sources",
  get_saved_company_intelligence: "Read saved company research",
  resolve_company_source: "Verify company job source",
};

export function ToolPart({ part }: { part: ToolChatPart }) {
  const label = TOOL_LABELS[part.name] ?? part.name.replaceAll("_", " ");
  const statusLabel = part.done ? (part.ok ? "Completed" : "Failed") : "Working";
  return (
    <Collapsible data-testid="chat-part-tool" className="min-w-0 py-2.5">
      <CollapsibleTrigger className="group/activity flex min-h-10 w-full items-center gap-3 rounded-lg px-1.5 text-left text-sm transition-colors duration-[160ms] ease-out-strong hover:bg-muted/55 focus-visible:outline-2 focus-visible:outline-offset-2">
        <span className="flex size-7 shrink-0 items-center justify-center rounded-full border bg-background shadow-sm">
        {!part.done ? (
          <Loader2 className="size-3.5 text-primary motion-safe:animate-spin" aria-hidden="true" />
        ) : part.ok ? (
          <Check className="agent-status-enter size-3.5 text-success" aria-hidden="true" />
        ) : (
          <X className="agent-status-enter size-3.5 text-destructive" aria-hidden="true" />
        )}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate font-medium capitalize text-foreground">{label}</span>
          <span className="flex min-w-0 items-center gap-2 text-[0.8125rem] leading-5 text-muted-foreground">
            <span className="shrink-0 text-[0.75rem] font-medium">{statusLabel}</span>
            {part.argsPreview ? <span className="truncate">{part.argsPreview}</span> : null}
          </span>
        </span>
        <span className="sr-only" aria-live="polite">{label}: {statusLabel}</span>
        <ChevronDown className="size-4 shrink-0 text-muted-foreground transition-transform duration-[180ms] ease-out-strong group-data-panel-open/activity:rotate-180 motion-reduce:transition-none" aria-hidden="true" />
      </CollapsibleTrigger>
      <CollapsibleContent keepMounted className="agent-disclosure overflow-hidden">
        <div className="ml-10 mt-1 flex items-start gap-2 border-l-2 border-primary/20 py-1 pl-3 font-mono text-[0.8125rem] leading-6 text-muted-foreground">
          <Wrench className="mt-1 size-3 shrink-0" aria-hidden="true" />
          <span className="min-w-0 whitespace-pre-wrap break-words">{part.resultPreview === "No result was returned." ? "No result was returned." : part.resultPreview || "Waiting for result…"}</span>
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}
