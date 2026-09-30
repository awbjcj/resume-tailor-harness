import { LayoutGrid, List } from "lucide-react";

import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import type { ViewMode } from "./use-view-mode";

export function BoardViewToggle({ view, onChange }: { view: ViewMode; onChange: (view: ViewMode) => void }) {
  return (
    <ToggleGroup
      aria-label="Board view"
      className="w-fit flex-nowrap gap-1 rounded-lg border bg-muted/70 p-1"
      value={[view]}
      onValueChange={(values) => {
        const next = values.at(-1);
        if (next === "cards" || next === "list") onChange(next);
      }}
    >
      <ToggleGroupItem value="cards" aria-label="Card view" className="h-8 rounded-md border-transparent bg-transparent px-3 text-muted-foreground shadow-none aria-pressed:border-border aria-pressed:bg-card aria-pressed:text-foreground aria-pressed:shadow-sm">
        <LayoutGrid aria-hidden="true" /> Cards
      </ToggleGroupItem>
      <ToggleGroupItem value="list" aria-label="List view" className="h-8 rounded-md border-transparent bg-transparent px-3 text-muted-foreground shadow-none aria-pressed:border-border aria-pressed:bg-card aria-pressed:text-foreground aria-pressed:shadow-sm">
        <List aria-hidden="true" /> List
      </ToggleGroupItem>
    </ToggleGroup>
  );
}
