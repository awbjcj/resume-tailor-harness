import { Navigate, useLocation } from "react-router-dom";

import { Field, FieldGroup, FieldLabel, FieldSet } from "@/components/ui/field";
import {
  findCatalogModel,
  ModelPicker,
  ModelTuningControls,
} from "../ModelPicker";
import { SecretsForm } from "../forms/SecretsForm";
import { SaveBar } from "../SaveBar";
import { useConfig, useSaveConfig } from "../use-config";
import { useDraft } from "../use-draft";
import { useModelCatalog } from "../use-model-catalog";
import { useSaveSecrets, useSecrets } from "../use-secrets";
import { SettingsPage, SettingsSection } from "../SettingsPage";

const AI_KEYS = new Set(["anthropicApiKey", "openaiApiKey", "geminiApiKey", "deepseekApiKey"]);

type ModelsDoc = {
  cheapModel: string;
  midModel: string;
  premiumModel: string;
  cheapReasoningEffort: string | null;
  midReasoningEffort: string | null;
  premiumReasoningEffort: string | null;
};

type ModelField = {
  key: "cheapModel" | "midModel" | "premiumModel";
  effortKey: "cheapReasoningEffort" | "midReasoningEffort" | "premiumReasoningEffort";
  label: string;
};

const MODEL_FIELDS: ModelField[] = [
  { key: "cheapModel", effortKey: "cheapReasoningEffort", label: "Cheap tier model" },
  { key: "midModel", effortKey: "midReasoningEffort", label: "Mid tier model" },
  { key: "premiumModel", effortKey: "premiumReasoningEffort", label: "Premium tier model" },
];

export function KeysSettingsPage() {
  const secrets = useSecrets();
  const saveSecrets = useSaveSecrets();
  const models = useConfig("/api/config/models");
  const saveModels = useSaveConfig("/api/config/models");
  const catalog = useModelCatalog();
  const { draft, setDraft, dirty, reset } = useDraft(models.data as ModelsDoc | undefined);
  const location = useLocation();

  // Preserve OAuth links created before Gmail moved to email settings.
  if (new URLSearchParams(location.search).has("gmail")) {
    return <Navigate to={`/settings/notifications${location.search}${location.hash}`} replace />;
  }

  const error = secrets.error ?? models.error;
  if (!secrets.data || !draft) return <SettingsPage title="API keys & models" loading={!error} error={error}
    onRetry={() => Promise.all([secrets.refetch(), models.refetch()])} />;
  const serviceKeys = secrets.data.filter((secret) => !AI_KEYS.has(secret.key) &&
    secret.key !== "googleOauthClientId" && secret.key !== "googleOauthClientSecret");

  return (
    <SettingsPage title="API keys & models" error={error} onRetry={() => Promise.all([secrets.refetch(), models.refetch()])} description="Connect your AI providers, then choose the models used by each tier.">
      <SettingsSection title="AI provider keys" description="Keys save individually. Saved keys show only their last four characters.">
        <SecretsForm statuses={secrets.data.filter((secret) => AI_KEYS.has(secret.key))} saving={saveSecrets.isPending}
          onSave={(patch) => saveSecrets.mutateAsync(patch)} />
      </SettingsSection>
      <SettingsSection title="Model tiers" description="Choose a model for each tier. Save these changes together below.">
        <FieldSet disabled={saveModels.isPending}>
        <FieldGroup className="gap-6">
          {MODEL_FIELDS.map((f) => {
            const model = findCatalogModel(catalog.data, draft[f.key]);
            return (
              <Field key={f.key}>
                <FieldLabel htmlFor={f.key}>{f.label}</FieldLabel>
                <ModelPicker
                  id={f.key}
                  value={draft[f.key]}
                  catalog={catalog.data}
                  onChange={(value) => {
                    const next = findCatalogModel(catalog.data, value);
                    setDraft({
                      ...draft,
                      [f.key]: value,
                      [f.effortKey]: next?.reasoningEfforts.includes(
                        draft[f.effortKey] ?? "",
                      )
                        ? draft[f.effortKey]
                        : null,
                    });
                  }}
                />
                {model && (
                  <ModelTuningControls
                    modelId={draft[f.key]}
                    reasoningEffort={draft[f.effortKey]}
                    catalog={catalog.data}
                    onReasoningEffortChange={(value) =>
                      setDraft({ ...draft, [f.effortKey]: value })
                    }
                  />
                )}
              </Field>
            );
          })}
        </FieldGroup>
        </FieldSet>
      </SettingsSection>
      {serviceKeys.length > 0 && <SettingsSection title="Discovery & service access" description="These credentials connect job sources and supporting services. Each key saves individually.">
        <SecretsForm statuses={serviceKeys} saving={saveSecrets.isPending} onSave={(patch) => saveSecrets.mutateAsync(patch)} />
      </SettingsSection>}
      <SaveBar dirty={dirty} saving={saveModels.isPending} canSave={MODEL_FIELDS.every((field) => draft[field.key].trim().length > 0)}
        onSave={() => saveModels.mutate(draft as never, { onSuccess: (saved) => setDraft(saved as ModelsDoc) })}
        onDiscard={reset} />
    </SettingsPage>
  );
}
