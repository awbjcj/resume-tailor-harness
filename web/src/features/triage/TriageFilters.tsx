import "@/i18n/interaction-copy-filters";
import { SearchIcon } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { ActiveFilterSummary } from "@/components/filters/ActiveFilterSummary";
import { FacetPopover } from "@/components/filters/FacetPopover";
import { Button } from "@/components/ui/button";
import {
  Field,
  FieldGroup,
  FieldLabel,
  FieldTitle,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import type { Facets } from "@/features/board/use-board-query";
import { SavedViewsControl } from "@/features/board/SavedViewsControl";
import { ImportJobsButton } from "@/features/runs/ImportJobsDialog";
import { ManualJobDialog } from "@/features/runs/ManualJobDialog";
import { facetLabel } from "@/i18n/facet-labels";
import {
  emptyFilterState,
  type FilterState,
} from "@/lib/filters/types";

const SET_FILTER_KEYS: (keyof FilterState)[] = [
  "source", "status", "remote", "sponsorship", "seniority",
  "employmentType", "industry", "country", "region", "city",
  "companySize", "skills",
];
const CONTROL_LABEL =
  "text-[0.65rem] font-semibold uppercase tracking-[0.1em] text-muted-foreground";

function countsWithSelected(
  counts: Record<string, number> | undefined,
  selected: Set<string>,
) {
  const next = { ...(counts ?? {}) };
  for (const value of selected) next[value] ??= 0;
  return next;
}

export function TriageFilters({
  filter, facets, total, archived, onArchivedChange, onChange,
}: {
  filter: FilterState;
  facets: Facets;
  total: number;
  archived: boolean;
  onArchivedChange: (archived: boolean) => void;
  onChange: (filter: FilterState) => void;
}) {
  const { t, i18n } = useTranslation();
  const staleOptions = [
    { value: "any", label: "Any age" },
    ...[7, 14, 30, 45, 60, 90].map((days) => ({
      value: String(days),
      label: `Older than ${days} days`,
    })),
  ];
  const [searchDraft, setSearchDraft] = useState(() => ({
    value: filter.q,
    committed: filter.q,
  }));
  const [reasonDraft, setReasonDraft] = useState(() => ({
    value: filter.rejectReason,
    committed: filter.rejectReason,
  }));
  const search =
    searchDraft.committed === filter.q ? searchDraft.value : filter.q;
  const rejectReason =
    reasonDraft.committed === filter.rejectReason
      ? reasonDraft.value
      : filter.rejectReason;
  const setSearch = (value: string) =>
    setSearchDraft({ value, committed: filter.q });
  const setRejectReason = (value: string) =>
    setReasonDraft({ value, committed: filter.rejectReason });

  const sourceCounts = countsWithSelected(facets.source, filter.source);
  const statusCounts = countsWithSelected(facets.status, filter.status);
  statusCounts.raw ??= 0;
  statusCounts.rejected ??= 0;

  const removeFilter = (key: keyof FilterState, value: string) => {
    if (SET_FILTER_KEYS.includes(key)) {
      const next = new Set(filter[key] as Set<string>);
      next.delete(value);
      onChange({ ...filter, [key]: next });
    } else if (key === "q") {
      setSearch("");
      onChange({ ...filter, q: "" });
    } else if (key === "rejectReason") {
      setRejectReason("");
      onChange({ ...filter, rejectReason: "" });
    } else if (key === "salaryMin") {
      onChange({ ...filter, salaryMin: null });
    } else if (key === "staleDays") {
      onChange({ ...filter, staleDays: null });
    } else if (key === "staleMinDays") {
      onChange({ ...filter, staleMinDays: null });
    }
  };

  const clearFilters = () => {
    setSearch("");
    setRejectReason("");
    const cleared = emptyFilterState();
    cleared.sort = "recency";
    onChange(cleared);
  };
  const hasDraftChanges =
    search.trim() !== filter.q ||
    rejectReason.trim() !== filter.rejectReason;

  return (
    <section aria-label="Triage filters" className="mb-5 @container/filters rounded-lg border bg-card p-4">
      <form id="triage-filters" onSubmit={(event) => {
        event.preventDefault();
        onChange({
          ...filter,
          q: search.trim(),
          rejectReason: rejectReason.trim(),
        });
      }}>
        <FieldGroup className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,11rem),1fr))] items-end gap-3">
          <Field className="min-w-0 gap-1.5">
            <FieldTitle className={CONTROL_LABEL}>Status</FieldTitle>
            <FacetPopover
              label="Status"
              counts={statusCounts}
              selected={filter.status}
              getLabel={(value) => facetLabel("status", value, i18n.resolvedLanguage)}
              onChange={(status) => onChange({ ...filter, status })}
              presentation="field"
            />
          </Field>

          <Field className="min-w-0 gap-1.5">
            <FieldTitle className={CONTROL_LABEL}>Source</FieldTitle>
            <FacetPopover
              label="Source"
              counts={sourceCounts}
              selected={filter.source}
              onChange={(source) => onChange({ ...filter, source })}
              presentation="field"
            />
          </Field>

          <Field className="min-w-0 gap-1.5">
            <FieldLabel htmlFor="triage-search" className={CONTROL_LABEL}>
              Search
            </FieldLabel>
            <div className="relative">
              <SearchIcon
                aria-hidden
                className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
              />
              <Input
                id="triage-search"
                type="search"
                placeholder="Title or company…"
                className="h-9 bg-background pl-8"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
            </div>
          </Field>

          <Field className="min-w-0 gap-1.5">
            <FieldLabel htmlFor="triage-reason" className={CONTROL_LABEL}>
              Rejection reason
            </FieldLabel>
            <Input
              id="triage-reason"
              type="search"
              placeholder="Sponsorship, salary, experience…"
              className="h-9 bg-background"
              value={rejectReason}
              onChange={(event) => setRejectReason(event.target.value)}
            />
          </Field>

          <Field className="min-w-0 gap-1.5">
            <FieldLabel htmlFor="triage-stale" className={CONTROL_LABEL}>
              Posted age
            </FieldLabel>
            <Select
              items={staleOptions}
              value={filter.staleMinDays == null ? "any" : String(filter.staleMinDays)}
              onValueChange={(value) => onChange({
                ...filter,
                staleMinDays: value === "any" ? null : Number(value),
              })}
            >
              <SelectTrigger id="triage-stale" size="compact" className="w-full bg-background">
                <SelectValue />
              </SelectTrigger>
              <SelectContent align="start" alignItemWithTrigger={false}>
                <SelectGroup>
                  {staleOptions.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectGroup>
              </SelectContent>
            </Select>
          </Field>
        </FieldGroup>
      </form>

      <div className="mt-3 grid items-end gap-3 border-t pt-3 @2xl/filters:grid-cols-[minmax(0,1fr)_auto]">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <div className="flex items-center gap-2">
            <Switch
              id="show-archived"
              checked={archived}
              onCheckedChange={onArchivedChange}
            />
            <Label htmlFor="show-archived" className="text-sm font-medium">
              Show archived
            </Label>
          </div>
          <div className="flex flex-wrap gap-2">
            <ManualJobDialog />
            <ImportJobsButton />
          </div>
        </div>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <span className="text-xs font-semibold tabular-nums text-muted-foreground">
            {t("interactionCopy.filters.matching", { count: total.toLocaleString() })}
          </span>
          <SavedViewsControl
            board="triage"
            filter={filter}
            defaultSort="recency"
            extraQuery={{ archived: archived ? "1" : undefined }}
            onApply={(nextFilter, params) => {
              onChange(nextFilter);
              onArchivedChange(params.get("archived") === "1");
            }}
          />
          <Button
            type="submit"
            form="triage-filters"
            size="sm"
            className="shrink-0"
            disabled={!hasDraftChanges}
          >
            Apply
          </Button>
        </div>
      </div>

      <ActiveFilterSummary
        filter={filter}
        onRemove={removeFilter}
        onClear={clearFilters}
      />
    </section>
  );
}
