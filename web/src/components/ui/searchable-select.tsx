import "@/i18n/long-list-copy";
import { useId, useMemo, type ReactNode, type RefObject } from "react";
import { Combobox } from "@base-ui/react/combobox";
import { Check, ChevronDown, Search } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Input } from "@/components/ui/input";
import { listSearch } from "@/lib/list-search";
import { cn } from "@/lib/utils";

export type SearchOption = {
  value: string;
  label: string;
  keywords?: string[];
  detail?: ReactNode;
  disabled?: boolean;
  title?: string;
};

export type SearchGroup = {
  id: string;
  label?: string;
  detail?: ReactNode;
  items: SearchOption[];
};

export function SearchableSelect({
  id,
  label,
  groups,
  value,
  onChange,
  placeholder,
  searchLabel,
  className,
  disabled,
  onOpenChange,
  loadingLabel,
  portalContainer,
}: {
  id?: string;
  label?: string;
  groups: SearchGroup[];
  value: string | null;
  onChange: (value: string) => void;
  placeholder?: string;
  searchLabel?: string;
  className?: string;
  disabled?: boolean;
  onOpenChange?: (open: boolean) => void;
  loadingLabel?: string;
  portalContainer?: RefObject<HTMLElement | null>;
}) {
  const { t } = useTranslation();
  const valueId = useId();
  const { items, byValue } = useMemo(() => {
    const items = groups.filter((group) => group.items.length > 0);
    const byValue = new Map(items.flatMap((group) =>
      group.items.map((option) => [option.value, { option, label: group.label }] as const),
    ));
    return { items, byValue };
  }, [groups]);
  const selected = value === null ? null : byValue.get(value)?.option ?? { value, label: value };
  const search = searchLabel ?? t("longLists.searchOptions");

  return (
    <Combobox.Root<SearchOption>
      items={items}
      value={selected}
      onValueChange={(option) => { if (option) onChange(option.value); }}
      onOpenChange={onOpenChange}
      disabled={disabled}
      isItemEqualToValue={(option, current) => option.value === current.value}
      filter={(option, query) => listSearch(query)(option.label, option.value, byValue.get(option.value)?.label, ...(option.keywords ?? []))}
      autoHighlight
    >
      <Combobox.Trigger
        id={id}
        aria-label={label}
        aria-describedby={selected && (id || label) ? valueId : undefined}
        data-slot="searchable-select-trigger"
        className={cn("flex min-h-10 w-full min-w-0 cursor-pointer items-center justify-between gap-2 rounded-lg border border-input bg-background px-3 py-2 text-left text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50 data-placeholder:text-muted-foreground dark:bg-input/30", className)}
      >
        <span id={valueId} className="min-w-0 [overflow-wrap:anywhere]"><Combobox.Value placeholder={placeholder} /></span>
        <ChevronDown aria-hidden className="size-4 shrink-0 text-muted-foreground" />
      </Combobox.Trigger>
      <Combobox.Portal container={portalContainer}>
        <Combobox.Positioner align="start" sideOffset={5} positionMethod={portalContainer ? "fixed" : undefined} className="isolate z-50">
          <Combobox.Popup aria-label={label ?? search} className="flex max-h-(--available-height) w-(--anchor-width) min-w-[min(16rem,var(--available-width),calc(100vw-2rem))] max-w-[min(var(--available-width),calc(100vw-2rem))] flex-col overflow-hidden rounded-lg bg-popover text-popover-foreground shadow-card-raised ring-1 ring-foreground/10">
            <div className="relative shrink-0 border-b p-2">
              <Search aria-hidden className="pointer-events-none absolute left-5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <Combobox.Input render={<Input />} aria-label={search} placeholder={search} className="h-11 pl-9" />
            </div>
            {loadingLabel ? <Combobox.Status className="px-3 py-2 text-sm text-muted-foreground">{loadingLabel}</Combobox.Status> : null}
            <Combobox.Empty className="px-3 py-4 text-sm text-muted-foreground empty:sr-only">{loadingLabel ? null : t("longLists.noMatches")}</Combobox.Empty>
            <Combobox.List className="min-h-0 overflow-y-auto overscroll-contain p-1.5 empty:p-0">
              {(group: SearchGroup) => (
                <Combobox.Group key={group.id} items={group.items} className="border-b pb-1 last:border-b-0 last:pb-0">
                  {group.label ? (
                    <Combobox.GroupLabel className="flex flex-wrap items-center justify-between gap-1 px-2 py-1.5 text-sm font-medium text-muted-foreground">
                      <span className="min-w-0 [overflow-wrap:anywhere]">{group.label}</span>{" "}{group.detail}
                    </Combobox.GroupLabel>
                  ) : null}
                  <Combobox.Collection>
                    {(option: SearchOption) => (
                      <Combobox.Item
                        key={option.value}
                        value={option}
                        disabled={option.disabled}
                        title={option.title}
                        className="flex min-h-11 cursor-pointer items-center gap-2 rounded-md px-2 py-2 text-sm outline-none select-none data-highlighted:bg-accent data-highlighted:text-accent-foreground data-disabled:cursor-not-allowed data-disabled:opacity-50"
                      >
                        <span className="min-w-0 flex-1 [overflow-wrap:anywhere]">{option.label}{option.detail ? <> {option.detail}</> : null}</span>
                        <span className="flex size-4 shrink-0 items-center justify-center text-primary" aria-hidden>
                          <Combobox.ItemIndicator render={<Check className="size-4" />} />
                        </span>
                      </Combobox.Item>
                    )}
                  </Combobox.Collection>
                </Combobox.Group>
              )}
            </Combobox.List>
          </Combobox.Popup>
        </Combobox.Positioner>
      </Combobox.Portal>
    </Combobox.Root>
  );
}
