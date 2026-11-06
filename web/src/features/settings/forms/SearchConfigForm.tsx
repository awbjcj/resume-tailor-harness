import { useMutation } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import {
  Accordion, AccordionContent, AccordionItem, AccordionTrigger,
} from "@/components/ui/accordion";
import { Field, FieldGroup, FieldLabel, FieldSet } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { TagListInput } from "@/components/ui/tag-list-input";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { api, unwrap } from "@/lib/api/client";
import type { paths } from "@/lib/api/schema";
import { SEARCH_LOCATION_NORMALIZATION_KEY, useSearchLocationNormalizationPending } from "../use-config";

export type SearchDoc =
  paths["/api/config/search"]["get"]["responses"][200]["content"]["application/json"];

const REMOTE_OPTIONS = [
  { value: "remote", label: "Remote" },
  { value: "hybrid", label: "Hybrid" },
  { value: "onsite", label: "On-site" },
];

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
    <FieldSet disabled={disabled} className="gap-5">
      <TagListInput id="keywords" label={t("tagList.search.keywords")} value={value.keywords ?? []}
        disabled={disabled} onChange={(v) => set("keywords", v)} placeholder={t("tagList.search.keywordExample")} />
      <TagListInput id="titles" label={t("tagList.search.titles")} value={value.titles ?? []}
        disabled={disabled} onChange={(v) => set("titles", v)} placeholder={t("tagList.search.titleExample")} />
      <TagListInput id="locations" label="Locations" value={value.locations ?? []}
        disabled={disabled} separator="semicolon"
        onChange={handleLocationsChange} placeholder={t("tagList.search.location")}
        description={normalizing ? t("tagList.search.normalizing") : undefined} />
      <Field>
        <FieldLabel>Remote policy</FieldLabel>
        <ToggleGroup
          value={value.remotePolicy ?? []}
          onValueChange={(next) => set("remotePolicy", next)}
        >
          {REMOTE_OPTIONS.map((o) => (
            <ToggleGroupItem key={o.value} value={o.value}>{o.label}</ToggleGroupItem>
          ))}
        </ToggleGroup>
      </Field>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Field>
          <FieldLabel htmlFor="minSalary">Minimum salary</FieldLabel>
          <Input id="minSalary" type="number" value={value.minSalary ?? ""}
            onChange={(e) => set("minSalary", numOrNull(e.target.value))} />
        </Field>
        <Field>
          <FieldLabel htmlFor="yoeMin">Years of experience, min</FieldLabel>
          <Input id="yoeMin" type="number" value={value.yoeMin ?? ""}
            onChange={(e) => set("yoeMin", numOrNull(e.target.value))} />
        </Field>
        <Field>
          <FieldLabel htmlFor="yoeMax">Years of experience, max</FieldLabel>
          <Input id="yoeMax" type="number" value={value.yoeMax ?? ""}
            onChange={(e) => set("yoeMax", numOrNull(e.target.value))} />
        </Field>
      </div>
      <Field>
        <div className="flex items-center gap-3">
          <Switch id="sponsorship" checked={value.sponsorshipRequired ?? false}
            onCheckedChange={(v: boolean) => set("sponsorshipRequired", v)} />
          <FieldLabel htmlFor="sponsorship">I need visa sponsorship</FieldLabel>
        </div>
      </Field>
      <Accordion>
        <AccordionItem value="tuning">
          <AccordionTrigger>Relevance tuning</AccordionTrigger>
          <AccordionContent>
            <FieldGroup>
              <TagListInput id="roleAnchors" label={t("tagList.search.roleAnchors")} value={value.roleAnchors ?? []}
                disabled={disabled} onChange={(v) => set("roleAnchors", v)} />
              <TagListInput id="excludeTerms" label={t("tagList.search.excludeTerms")} value={value.excludeTerms ?? []}
                disabled={disabled} onChange={(v) => set("excludeTerms", v)} />
              <Field>
                <FieldLabel htmlFor="targetRole">Target role</FieldLabel>
                <Input id="targetRole" value={value.targetRole ?? ""}
                  onChange={(e) => set("targetRole", e.target.value || null)} />
              </Field>
            </FieldGroup>
          </AccordionContent>
        </AccordionItem>
      </Accordion>
    </FieldSet>
  );
}
