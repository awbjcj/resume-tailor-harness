import { Navigate, useLocation } from "react-router-dom";

import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
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

  if (!secrets.data || !draft) return <Skeleton className="h-64 w-full" />;

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="text-lg font-semibold">API keys & models</h1>
        <p className="text-sm text-muted-foreground">
          Keys are write-only: once saved, only the last four characters are shown.
        </p>
      </header>
      <SecretsForm statuses={secrets.data.filter((secret) =>
        secret.key !== "googleOauthClientId" && secret.key !== "googleOauthClientSecret",
      )} saving={saveSecrets.isPending}
        onSave={(patch) => saveSecrets.mutate(patch)} />
      <Separator />
      <section className="flex flex-col gap-4">
        <h2 className="text-sm font-medium">Model tiers</h2>
        <FieldGroup>
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
        <SaveBar dirty={dirty} saving={saveModels.isPending}
          onSave={() => saveModels.mutate(draft as never)}
          onDiscard={reset} />
      </section>
    </div>
  );
}
