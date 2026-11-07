import { useState, type ReactNode } from "react";
import { ChevronDown } from "lucide-react";

/** Keep optional fields mounted so collapsing a section never discards edits. */
export function SettingsDisclosure({ title, description, defaultOpen = false, children }: {
  title: string;
  description?: string;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <details open={open} onToggle={(event) => setOpen(event.currentTarget.open)} className="group/disclosure min-w-0 border-t pt-5">
      <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 rounded-md text-base font-semibold outline-none focus-visible:ring-2 focus-visible:ring-ring [&::-webkit-details-marker]:hidden">
        <h2 className="min-w-0 [overflow-wrap:anywhere]">{title}</h2>
        <ChevronDown aria-hidden="true" className="size-4 shrink-0 text-muted-foreground transition-transform group-open/disclosure:rotate-180 motion-reduce:transition-none" />
      </summary>
      <div className="flex min-w-0 flex-col gap-5 pt-3">
        {description && <p className="max-w-prose text-sm leading-relaxed text-muted-foreground">{description}</p>}
        {children}
      </div>
    </details>
  );
}
