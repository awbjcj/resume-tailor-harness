import { useState, type ComponentProps, type ReactNode } from "react";
import { ChevronRight } from "lucide-react";

import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";

const headingTags = { 3: "h3", 4: "h4" } as const;

export function ListSection({
  label,
  count,
  defaultOpen = false,
  browseOpen,
  onBrowseOpenChange,
  query = "",
  level = 3,
  actions,
  children,
  className,
  ...props
}: ComponentProps<"section"> & {
  label: string;
  count: number;
  defaultOpen?: boolean;
  browseOpen?: boolean;
  onBrowseOpenChange?: (open: boolean) => void;
  query?: string;
  level?: 3 | 4;
  actions?: ReactNode;
}) {
  const Heading = headingTags[level];
  const [browsing, setBrowsing] = useState<boolean>();
  const [searching, setSearching] = useState<{ query: string; open: boolean }>();
  if (searching && searching.query !== query) setSearching(undefined);
  const open = query
    ? searching?.query !== query || searching.open
    : browseOpen ?? browsing ?? defaultOpen;
  return (
    <Collapsible
      render={<section {...props} />}
      className={cn("min-w-0", className)}
      open={open}
      onOpenChange={(next) => {
        if (query) setSearching({ query, open: next });
        else if (onBrowseOpenChange) onBrowseOpenChange(next);
        else setBrowsing(next);
      }}
    >
      <div className="flex min-w-0 items-center gap-1">
        <Heading className="min-w-0 flex-1">
          <CollapsibleTrigger
            type="button"
            className="flex min-h-11 w-full min-w-0 cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-left text-sm font-semibold outline-none hover:bg-muted/55 focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring active:bg-muted/75"
          >
            <ChevronRight aria-hidden className={cn("size-4 shrink-0 text-muted-foreground", open && "rotate-90")} />
            <span className="min-w-0 flex-1 [overflow-wrap:anywhere]">{label}</span>{" "}
            <span className="shrink-0 text-xs font-normal tabular-nums text-muted-foreground">{count}</span>
          </CollapsibleTrigger>
        </Heading>
        {actions}
      </div>
      <CollapsibleContent>{children}</CollapsibleContent>
    </Collapsible>
  );
}
