import { useEffect, useRef, useState, type FormEvent } from "react";
import { Eye, EyeOff } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { providerSetupEn } from "@/i18n/provider-setup";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldDescription, FieldError, FieldLabel, FieldSet } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { SecretsForm } from "@/features/settings/forms/SecretsForm";
import { useDraft } from "@/features/settings/use-draft";
import { useSaveSecrets, useSecrets } from "@/features/settings/use-secrets";
import { ApiError } from "@/lib/api/client";
import { cn } from "@/lib/utils";
import { useSetupContinuation } from "../use-setup-continuation";
import { useSaveSetupProvider, useSetupProvider, type SetupProvider } from "../use-setup-provider";

const issues = {
  INVALID_PROVIDER: ["provider", "invalidProvider"],
  PROVIDER_UNAVAILABLE: ["provider", "unavailable"],
  INVALID_BASE_URL: ["url", "invalidUrl"],
  INVALID_MODEL_ID: ["model", "invalidModel"],
  API_KEY_REQUIRED: ["key", "requiredKey"],
  INVALID_API_KEY: ["key", "invalidKey"],
  CUSTOM_ENDPOINT_UNAVAILABLE: ["error", "customUnavailable"],
  SAVE_FAILED: ["error", "saveError"],
} as const;

type IssueCode = keyof typeof issues;
type Issue = (typeof issues)[IssueCode];
type FieldName = Issue[0];

function providerDraft(provider: string, savedEndpoint: SetupProvider["customEndpoint"]) {
  const endpoint = savedEndpoint?.provider === provider ? savedEndpoint : null;
  return {
    provider,
    custom: endpoint?.selected ?? false,
    url: endpoint?.baseUrl ?? "",
    modelId: endpoint?.modelId ?? "",
    key: "",
  };
}

function ProviderForm({ config, next }: { config: SetupProvider; next: () => void }) {
  const { t } = useTranslation();
  const save = useSaveSetupProvider();
  const secrets = useSecrets();
  const saveSecrets = useSaveSecrets();
  const form = useRef<HTMLFormElement>(null);
  const initialProvider = config.selectedProvider ?? "";
  const savedEndpoint = config.customEndpoint;
  const initial = providerDraft(initialProvider, savedEndpoint);
  const { draft, setDraft, reset } = useDraft(initial);
  const values = draft ?? initial;
  const { provider, custom, url, modelId, key } = values;
  const [showKey, setShowKey] = useState(false);
  const [issue, setIssue] = useState<Issue | null>(null);
  const saving = save.isPending;
  const busy = saving || saveSecrets.isPending;
  const keepEndpointKey = custom && savedEndpoint?.provider === provider
    && savedEndpoint.baseUrl === url.trim().replace(/\/+$/, "");
  const providerAvailable = config.providers.some((choice) => choice.id === provider && choice.available);
  const needsKey = custom ? !keepEndpointKey : !providerAvailable;
  const unchanged = config.modelTiersReady && provider === initialProvider && !key.trim()
    && custom === initial.custom
    && (!custom || (keepEndpointKey && modelId.trim() === initial.modelId));

  useEffect(() => {
    if (issue && !save.isPending) {
      form.current?.querySelector<HTMLElement>(`#initial-provider-${issue[0]}`)?.focus();
    }
  }, [issue, save.isPending]);

  const invalid = (field: FieldName) => issue?.[0] === field;
  const errorText = (field: FieldName) => invalid(field) && issue && (
    <FieldError id={`initial-provider-${field}-error`}>{t(`providerSetup.${issue[1]}`)}</FieldError>
  );
  const descriptions = (field: FieldName, hasHelp = true) => [
    hasHelp ? `initial-provider-${field}-help` : "",
    invalid(field) ? `initial-provider-${field}-error` : "",
  ].filter(Boolean).join(" ") || undefined;

  function edit(patch: Partial<typeof values>, field: FieldName) {
    setDraft({ ...values, ...patch });
    if (issue?.[0] === field || issue?.[0] === "error" || (field === "url" && issue?.[0] === "key")) {
      setIssue(null);
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setIssue(null);
    if (unchanged) {
      next();
      return;
    }
    if (!provider) return setIssue(issues.INVALID_PROVIDER);
    if (custom && !url.trim()) return setIssue(issues.INVALID_BASE_URL);
    if (custom && !modelId.trim()) return setIssue(issues.INVALID_MODEL_ID);
    if (needsKey && !key.trim()) return setIssue(issues.API_KEY_REQUIRED);
    try {
      await save.mutateAsync({
        provider,
        ...(key.trim() ? { apiKey: key.trim() } : {}),
        ...(custom ? { baseUrl: url.trim(), modelId: modelId.trim() } : {}),
      });
      if (form.current) {
        reset();
        next();
      }
    } catch (failure) {
      setIssue(failure instanceof ApiError && Object.hasOwn(issues, failure.code)
        ? issues[failure.code as IssueCode] : issues.SAVE_FAILED);
    } finally {
      save.reset();
    }
  }

  const optionalCredentials = (secrets.data ?? []).filter((status) =>
    !config.providers.some((choice) => status.key === `${choice.id}ApiKey`),
  );

  return (
    <>
      <CardContent className="space-y-5">
        <form id="initial-provider-form" ref={form} onSubmit={(event) => void submit(event)} noValidate>
          <FieldSet disabled={busy} aria-busy={saving}>
            <Field>
              <FieldLabel htmlFor="initial-provider-provider">{t(custom ? "providerSetup.apiFormat" : "providerSetup.provider")}</FieldLabel>
              <select id="initial-provider-provider" className="min-h-11 min-w-0 rounded-lg border border-input bg-card px-3 text-base shadow-xs outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/20 disabled:opacity-50 aria-invalid:border-destructive dark:bg-input/30"
                value={provider} aria-invalid={invalid("provider")} aria-describedby={descriptions("provider", false)}
                onChange={(event) => {
                  setDraft(providerDraft(event.target.value, savedEndpoint));
                  setShowKey(false);
                  setIssue(null);
                }}>
                {initialProvider === "" && <option value="">{t("providerSetup.keepCurrent")}</option>}
                {config.providers.map((choice) => <option key={choice.id} value={choice.id}>{choice.label}</option>)}
              </select>
              {errorText("provider")}
            </Field>
            {provider && config.customEndpointAllowed && (
              <label className="flex min-h-11 cursor-pointer items-center gap-3 rounded-lg border px-3 py-2 text-sm font-medium">
                <input type="checkbox" checked={custom} className="size-4 shrink-0 accent-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
                  onChange={(event) => {
                    setDraft({ ...values, custom: event.target.checked, key: "" });
                    setShowKey(false);
                    setIssue(null);
                  }} />
                {t("providerSetup.custom")}
              </label>
            )}
            {custom && (
              <>
                <Field>
                  <FieldLabel htmlFor="initial-provider-url">{t("providerSetup.baseUrl")}</FieldLabel>
                  <Input id="initial-provider-url" className="min-h-11" type="url" required maxLength={2048}
                    autoComplete="url" autoCapitalize="none" spellCheck={false}
                    value={url} onChange={(event) => edit({ url: event.target.value }, "url")}
                    aria-invalid={invalid("url")} aria-describedby={descriptions("url")} />
                  <FieldDescription id="initial-provider-url-help">{t(`providerSetup.baseUrlHelp.${provider as keyof typeof providerSetupEn.baseUrlHelp}`)}</FieldDescription>
                  {errorText("url")}
                </Field>
                <Field>
                  <FieldLabel htmlFor="initial-provider-model">{t("providerSetup.modelId")}</FieldLabel>
                  <Input id="initial-provider-model" className="min-h-11" required maxLength={256}
                    autoCapitalize="none" spellCheck={false} value={modelId} onChange={(event) => edit({ modelId: event.target.value }, "model")}
                    aria-invalid={invalid("model")} aria-describedby={descriptions("model")} />
                  <FieldDescription id="initial-provider-model-help">{t("providerSetup.modelHelp")}</FieldDescription>
                  {errorText("model")}
                </Field>
              </>
            )}
            {provider && (
              <Field>
                <FieldLabel htmlFor="initial-provider-key">{t(needsKey ? "providerSetup.apiKey" : "providerSetup.optionalKey")}</FieldLabel>
                <div className="relative">
                  <Input id="initial-provider-key" className="min-h-11 pr-12" type={showKey ? "text" : "password"}
                    required={needsKey} maxLength={4096} autoComplete="new-password" autoCapitalize="none" spellCheck={false}
                    value={key} onChange={(event) => edit({ key: event.target.value }, "key")} aria-invalid={invalid("key")}
                    aria-describedby={descriptions("key", !needsKey)} />
                  <Button type="button" variant="ghost" size="icon-lg" className="absolute inset-y-0 right-0 min-h-11 min-w-11"
                    aria-label={t(showKey ? "providerSetup.hideKey" : "providerSetup.showKey")}
                    aria-pressed={showKey} onClick={() => setShowKey(!showKey)}>
                    {showKey ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}
                  </Button>
                </div>
                {!needsKey && <FieldDescription id="initial-provider-key-help">{t(keepEndpointKey ? "providerSetup.savedEndpointKey" : "providerSetup.availableKey")}</FieldDescription>}
                {errorText("key")}
              </Field>
            )}
          </FieldSet>
          {issue?.[0] === "error" && <FieldError id="initial-provider-error" tabIndex={-1} className="mt-4">{t(`providerSetup.${issue[1]}`)}</FieldError>}
        </form>
        {optionalCredentials.length > 0 && (
          <Accordion>
            <AccordionItem value="more">
              <AccordionTrigger>{t("providerSetup.optionalCredentials")}</AccordionTrigger>
              <AccordionContent>
                <SecretsForm statuses={optionalCredentials} saving={busy} onSave={(patch) => saveSecrets.mutateAsync(patch)} />
              </AccordionContent>
            </AccordionItem>
          </Accordion>
        )}
      </CardContent>
      <CardFooter className="flex flex-wrap justify-end gap-2">
        <Button variant="ghost" className="min-h-11" disabled={busy} onClick={next}>{t("providerSetup.skip")}</Button>
        <Button type="submit" form="initial-provider-form" className="min-h-11" disabled={busy}>
          <span className="inline-grid place-items-center">
            <span className={cn("col-start-1 row-start-1", saving && "invisible")} aria-hidden={saving}>
              {t(unchanged ? "providerSetup.continue" : "providerSetup.save")}
            </span>
            <span className={cn("col-start-1 row-start-1 inline-flex items-center gap-2", !saving && "invisible")} aria-hidden={!saving}>
              {saving ? <Spinner aria-hidden="true" /> : <span className="size-4" />}
              {t("providerSetup.saving")}
            </span>
          </span>
        </Button>
        <span role="status" className="sr-only">{saving ? t("providerSetup.saving") : ""}</span>
      </CardFooter>
    </>
  );
}

export function KeysStep() {
  const { t } = useTranslation();
  const config = useSetupProvider();
  const navigate = useNavigate();
  const { nextPath } = useSetupContinuation();
  const next = () => navigate(nextPath("keys"));

  return (
    <Card>
      <CardHeader>
        <CardTitle><h1>{t("providerSetup.title")}</h1></CardTitle>
        <CardDescription>{t("providerSetup.description")}</CardDescription>
      </CardHeader>
      {config.data ? <ProviderForm config={config.data} next={next} /> : (
        <>
          <CardContent>
            {config.isError ? <FieldError>{t("providerSetup.loadError")}</FieldError>
              : <p className="text-sm text-muted-foreground" role="status">{t("providerSetup.loading")}</p>}
          </CardContent>
          <CardFooter className="flex flex-wrap justify-end gap-2">
            <Button variant="ghost" className="min-h-11" onClick={next}>{t("providerSetup.skip")}</Button>
            {config.isError && <Button className="min-h-11" disabled={config.isFetching} onClick={() => void config.refetch()}>{t("providerSetup.retry")}</Button>}
          </CardFooter>
        </>
      )}
    </Card>
  );
}
