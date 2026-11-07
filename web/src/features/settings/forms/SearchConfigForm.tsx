import { useMutation } from "@tanstack/react-query";
import { useId } from "react";
import { useTranslation } from "react-i18next";

import {
  Accordion, AccordionContent, AccordionItem, AccordionTrigger,
} from "@/components/ui/accordion";
import { Field, FieldGroup, FieldLabel, FieldSet, FieldTitle, FieldError } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { TagListInput } from "@/components/ui/tag-list-input";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { api, unwrap } from "@/lib/api/client";
import type { paths } from "@/lib/api/schema";
import { SEARCH_LOCATION_NORMALIZATION_KEY, useSearchLocationNormalizationPending } from "../use-config";
import { SettingsSection } from "../SettingsPage";

export type SearchDoc =
  paths["/api/config/search"]["get"]["responses"][200]["content"]["application/json"];

const REMOTE_OPTIONS = [
  { value: "remote", label: "Remote" },
  { value: "hybrid", label: "Hybrid" },
  { value: "onsite", label: "On-site" },
];

const FIELD_LABEL_CLASS = "text-[0.95rem] leading-5 [overflow-wrap:anywhere]";

function numOrNull(raw: string): number | null {
  return raw === "" ? null : Number(raw);
}

export function SearchConfigForm({
  value, onChange, disabled = false,
}: {
  value: SearchDoc;
  onChange: (update: (current: SearchDoc) => SearchDoc) => void;
  disabled?: boolean;
}) {
  const { t } = useTranslation();
  const remotePolicyLabelId = useId();
  const normalizing = useSearchLocationNormalizationPending();
  const set = <K extends keyof SearchDoc>(key: K, v: SearchDoc[K]) =>
    onChange((current) => ({ ...current, [key]: v }));

  const normalizeLocations = useMutation({
    mutationKey: SEARCH_LOCATION_NORMALIZATION_KEY,
    mutationFn: (raw: string[]) =>
      unwrap(
        api.POST("/api/config/search/normalize-locations", { body: { raw } }),
      ),
    onSuccess: ({ normalized = [] }, added) => {
      const canonical = new Map(added.map((raw, index) => [raw, normalized[index]]));
      // Apply each response to the latest draft. Removed values stay removed.
      onChange((current) => {
        if (!current.locations?.some((location) => canonical.has(location))) return current;
        return {
          ...current,
          locations: [...new Set(current.locations.map((location) => canonical.get(location) || location))],
        };
      });
    },
  });

  const handleLocationsChange = (next: string[]) => {
    const added = next.filter((location) => !value.locations?.includes(location));
    set("locations", next);
    if (added.length) normalizeLocations.mutate(added);
  };

  return (
    <FieldSet disabled={disabled} className="@container/search-config gap-7">
      <SettingsSection title="Roles to look for" description="Use keywords for skills or topics, and job titles for the positions you want.">
      <div className="grid min-w-0 gap-5 @lg/search-config:grid-cols-2">
      <TagListInput id="keywords" label={t("tagList.search.keywords")} value={value.keywords ?? []}
        disabled={disabled} onChange={(v) => set("keywords", v)} placeholder={t("tagList.search.keywordExample")} />
      <TagListInput id="titles" label={t("tagList.search.titles")} value={value.titles ?? []}
        disabled={disabled} onChange={(v) => set("titles", v)} placeholder={t("tagList.search.titleExample")} />
      </div>
      </SettingsSection>
      <SettingsSection title="Location & work preferences" description="Choose where and how you want to work.">
      <TagListInput id="locations" label="Locations" value={value.locations ?? []}
        disabled={disabled} separator="semicolon"
        onChange={handleLocationsChange} placeholder={t("tagList.search.location")}
        description={normalizing ? t("tagList.search.normalizing") : undefined} />
      <Field>
        <FieldTitle id={remotePolicyLabelId} className={FIELD_LABEL_CLASS}>Remote policy</FieldTitle>
        <ToggleGroup
          aria-labelledby={remotePolicyLabelId}
          value={value.remotePolicy ?? []}
          onValueChange={(next) => set("remotePolicy", next)}
        >
          {REMOTE_OPTIONS.map((o) => (
            <ToggleGroupItem
              key={o.value}
              value={o.value}
              className="h-auto min-h-11 max-w-full px-3.5 py-2 text-[0.95rem] leading-5 whitespace-normal [overflow-wrap:anywhere]"
            >
              {o.label}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      </Field>
      <Field>
        <div className="flex min-h-11 items-center gap-3">
          <Switch id="sponsorship" checked={value.sponsorshipRequired ?? false}
            onCheckedChange={(v: boolean) => set("sponsorshipRequired", v)} />
          <FieldLabel htmlFor="sponsorship" className={FIELD_LABEL_CLASS}>I need visa sponsorship</FieldLabel>
        </div>
      </Field>
      </SettingsSection>
      <SettingsSection title="Salary & experience" description="Leave a limit blank when you do not want to filter by it.">
      <div className="grid grid-cols-1 items-end gap-4 @lg/search-config:grid-cols-3">
        <Field>
          <FieldLabel htmlFor="minSalary" className={FIELD_LABEL_CLASS}>Minimum salary</FieldLabel>
          <Input id="minSalary" type="number" min={0} className="h-11" value={value.minSalary ?? ""}
            onChange={(e) => set("minSalary", numOrNull(e.target.value))} />
        </Field>
        <Field>
          <FieldLabel htmlFor="yoeMin" className={FIELD_LABEL_CLASS}>Years of experience, min</FieldLabel>
          <Input id="yoeMin" type="number" min={0} className="h-11" value={value.yoeMin ?? ""}
            onChange={(e) => set("yoeMin", numOrNull(e.target.value))} />
        </Field>
        <Field>
          <FieldLabel htmlFor="yoeMax" className={FIELD_LABEL_CLASS}>Years of experience, max</FieldLabel>
          <Input id="yoeMax" type="number" min={0} className="h-11" value={value.yoeMax ?? ""}
            onChange={(e) => set("yoeMax", numOrNull(e.target.value))} />
        </Field>
      </div>
      {value.yoeMin != null && value.yoeMax != null && value.yoeMin > value.yoeMax &&
        <FieldError>Minimum cannot exceed the maximum.</FieldError>}
      </SettingsSection>
      <Accordion>
        <AccordionItem value="tuning">
          <AccordionTrigger className="min-h-11 min-w-0 items-center gap-2 text-[0.95rem] leading-5 [overflow-wrap:anywhere]">Relevance tuning</AccordionTrigger>
          <AccordionContent>
            <FieldGroup>
              <TagListInput id="roleAnchors" label={t("tagList.search.roleAnchors")} value={value.roleAnchors ?? []}
                disabled={disabled} onChange={(v) => set("roleAnchors", v)} />
              <TagListInput id="excludeTerms" label={t("tagList.search.excludeTerms")} value={value.excludeTerms ?? []}
                disabled={disabled} onChange={(v) => set("excludeTerms", v)} />
              <Field>
                <FieldLabel htmlFor="targetRole" className={FIELD_LABEL_CLASS}>Target role</FieldLabel>
                <Input id="targetRole" className="h-11" value={value.targetRole ?? ""}
                  onChange={(e) => set("targetRole", e.target.value || null)} />
              </Field>
            </FieldGroup>
          </AccordionContent>
        </AccordionItem>
      </Accordion>
    </FieldSet>
  );
}
