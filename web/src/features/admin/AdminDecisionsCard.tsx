import "@/i18n/decisions";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { api, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

const queryKey = ["admin", "decisions"];

export function AdminDecisionsCard() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const config = useQuery({ queryKey, queryFn: () => unwrap(api.GET("/api/admin/routing/decisions")) });
  const [enabledDraft, setEnabled] = useState<boolean | null>(null);
  const [keyDraft, setKey] = useState<string | null | undefined>(undefined);
  const save = useMutation({
    mutationFn: (body: components["schemas"]["DecisionsUpdate"]) => unwrap(api.PUT("/api/admin/routing/decisions", { body })),
    onSuccess: (data) => {
      queryClient.setQueryData(queryKey, data);
      setEnabled(null);
      setKey(undefined);
    },
  });
  const enabled = enabledDraft ?? config.data?.enabled ?? false;
  const hasKey = keyDraft === undefined ? config.data?.keyConfigured : Boolean(keyDraft?.trim());
  const dirty = (enabledDraft !== null && enabledDraft !== config.data?.enabled) || keyDraft !== undefined;
  const canSave = dirty && (!enabled || hasKey) && !save.isPending;
  const discard = () => { setEnabled(null); setKey(undefined); save.reset(); };

  return (
    <Card>
      <CardHeader>
        <CardTitle><h2>{t("decisions.title")}</h2></CardTitle>
        <CardDescription>{t("decisions.description")}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {config.isPending ? <p role="status">{t("decisions.loading")}</p> : config.isError ? (
          <Alert variant="destructive"><AlertDescription>
            {t("decisions.loadError")}
            <Button variant="outline" onClick={() => void config.refetch()}>{t("decisions.retry")}</Button>
          </AlertDescription></Alert>
        ) : (
          <>
            <p id="decisions-billing" className="text-sm text-muted-foreground">{t("decisions.billing")}</p>
            <div className="flex items-start justify-between gap-4">
              <FieldLabel htmlFor="decisions-enabled">{t("decisions.enrollment")}</FieldLabel>
              <Switch id="decisions-enabled" checked={enabled} disabled={save.isPending} aria-describedby="decisions-billing" onCheckedChange={setEnabled} />
            </div>
            <Field>
              <FieldLabel htmlFor="decisions-api-key">{t("decisions.key")}</FieldLabel>
              <Input id="decisions-api-key" type="password" autoComplete="new-password" value={keyDraft ?? ""} disabled={save.isPending}
                placeholder={t(config.data?.keyConfigured && keyDraft === undefined ? "decisions.configured" : "decisions.placeholder")}
                onChange={(event) => setKey(event.target.value || undefined)} />
              <FieldDescription>{t("decisions.keyHelp")}</FieldDescription>
            </Field>
            {config.data?.keyConfigured && keyDraft !== null ? <Button className="self-start" variant="outline" disabled={save.isPending} onClick={() => { setKey(null); setEnabled(false); }}>{t("decisions.clear")}</Button> : null}
            {keyDraft === null ? <p role="status" className="text-sm">{t("decisions.cleared")}</p> : null}
            {enabled && !hasKey ? <p role="status" className="text-sm text-destructive">{t("decisions.missingKey")}</p> : null}
            <p className="text-sm text-muted-foreground">{t("decisions.quality")}</p>
            <p className="text-xs text-muted-foreground">{t("decisions.route")}</p>
            {save.isError ? <Alert variant="destructive"><AlertDescription>{t("decisions.saveError")}</AlertDescription></Alert> : null}
            {save.isSuccess && !dirty ? <p role="status" className="text-sm">{t("decisions.saved")}</p> : null}
            <div className="flex flex-wrap gap-2">
              <Button disabled={!canSave} onClick={() => save.mutate({ enabled, ...(keyDraft !== undefined ? { apiKey: keyDraft } : {}) })}>{t(save.isPending ? "decisions.saving" : "decisions.save")}</Button>
              {dirty ? <Button variant="outline" disabled={save.isPending} onClick={discard}>{t("decisions.discard")}</Button> : null}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
