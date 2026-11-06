import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { reasoningEffortLabel } from "@/i18n/model-labels";
import { SearchableSelect } from "@/components/ui/searchable-select";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { DeepSeekPricingBadge } from "./DeepSeekPricingBadge";
import type { ProviderModelCatalog } from "./use-model-catalog";

const CUSTOM_VALUE = "__custom__";
const PROVIDER_DEFAULT = "__provider_default__";
const TUNING_LABEL_CLASS =
  "text-[0.68rem] font-semibold uppercase tracking-[0.12em] text-muted-foreground";

type ModelEntry = ProviderModelCatalog["models"][number];

export function findCatalogModel(
  catalog: ProviderModelCatalog[] | undefined,
  modelId: string,
) {
  return (catalog ?? []).flatMap((provider) => provider.models)
    .find((model) => model.id === modelId);
}

function CapabilityBadges({ model }: { model: ModelEntry }) {
  const { t } = useTranslation();
  if (!model.supportsReasoning && !model.supportsNativeSearch) return null;
  return (
    <span className="mt-1 flex flex-wrap gap-1">
      {model.supportsReasoning && (
        <Badge variant="outline" className="px-1.5 py-0 text-[10px] font-normal">
          {t("model.capabilities.reasoning")}
        </Badge>
      )}
      {model.supportsNativeSearch && (
        <Badge variant="outline" className="px-1.5 py-0 text-[10px] font-normal">
          {t("model.capabilities.search")}
        </Badge>
      )}
    </span>
  );
}

export function ModelPicker({
  id, value, onChange, catalog,
}: {
  id?: string;
  value: string;
  onChange: (value: string) => void;
  catalog: ProviderModelCatalog[] | undefined;
}) {
  const { t } = useTranslation();
  const allModels = useMemo(() => (catalog ?? []).flatMap((p) => p.models), [catalog]);
  const knownIds = useMemo(() => new Set(allModels.map((m) => m.id)), [allModels]);
  // Explicit escape hatch: once the user picks "Custom model id…", stay in
  // custom mode even while they clear/retype the field to something empty or
  // (transiently) matching a catalog id — only picking a real dropdown item
  // exits custom mode.
  const [customValue, setCustomValue] = useState<string | null>(null);
  const catalogReady = catalog !== undefined;
  const isCustom =
    customValue === value ||
    (catalogReady && value !== "" && !knownIds.has(value));
  return (
    <div className="flex flex-col gap-2">
      <SearchableSelect
        id={id}
        label={id ? undefined : t("model.select")}
        placeholder={t("model.select")}
        searchLabel={t("longLists.searchModels")}
        value={isCustom ? CUSTOM_VALUE : value || null}
        onChange={(selected) => {
          if (selected === CUSTOM_VALUE) {
            setCustomValue(value);
            return;
          }
          setCustomValue(null);
          onChange(selected);
        }}
        groups={[
          ...(catalog ?? []).map((provider) => ({
            id: provider.provider,
            label: provider.label,
            detail: (
              <span className="flex flex-wrap items-center gap-1.5">
                {provider.provider === "deepseek" ? <DeepSeekPricingBadge /> : null}
                {!provider.hasKey ? (
                  <Badge variant="outline" className="px-1.5 py-0 text-[10px] font-normal">
                    {t("model.noKey")}
                  </Badge>
                ) : null}
              </span>
            ),
            items: provider.models.map((model) => ({
              value: model.id,
              label: model.label,
              disabled: !provider.hasKey,
              detail: <CapabilityBadges model={model} />,
              title: !provider.hasKey ? t("model.addProviderKey", { provider: provider.label }) : undefined,
            })),
          })),
          { id: CUSTOM_VALUE, items: [{ value: CUSTOM_VALUE, label: t("model.customModelId") }] },
        ]}
      />
      {isCustom && (
        <Input
          aria-label={t("model.customModelId")}
          value={value}
          placeholder={t("model.customModelPlaceholder")}
          onChange={(e) => {
            setCustomValue(e.target.value);
            onChange(e.target.value);
          }}
        />
      )}
    </div>
  );
}

function TuningToggleGroup({
  label,
  value,
  levels,
  onChange,
}: {
  label: string;
  value: string | null;
  levels: string[];
  onChange: (value: string | null) => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className={TUNING_LABEL_CLASS}>{label}</span>
      <ToggleGroup
        aria-label={label}
        value={[value ?? PROVIDER_DEFAULT]}
        onValueChange={(next) => {
          const picked = next.at(-1);
          if (!picked) return;
          onChange(picked === PROVIDER_DEFAULT ? null : picked);
        }}
      >
        <ToggleGroupItem value={PROVIDER_DEFAULT} className="h-7 rounded-full px-2.5 text-xs">
          {t("model.providerDefault")}
        </ToggleGroupItem>
        {levels.map((level) => (
          <ToggleGroupItem key={level} value={level} className="h-7 rounded-full px-2.5 text-xs">
            {reasoningEffortLabel(t, level)}
          </ToggleGroupItem>
        ))}
      </ToggleGroup>
    </div>
  );
}

export function ModelTuningControls({
  modelId,
  reasoningEffort,
  catalog,
  onReasoningEffortChange,
}: {
  modelId: string;
  reasoningEffort: string | null;
  catalog: ProviderModelCatalog[] | undefined;
  onReasoningEffortChange: (value: string | null) => void;
}) {
  const { t } = useTranslation();
  const model = findCatalogModel(catalog, modelId);
  if (!model || model.reasoningEfforts.length === 0) return null;

  return (
    <TuningToggleGroup
      label={t("model.reasoningEffort")}
      value={reasoningEffort}
      levels={model.reasoningEfforts}
      onChange={onReasoningEffortChange}
    />
  );
}
