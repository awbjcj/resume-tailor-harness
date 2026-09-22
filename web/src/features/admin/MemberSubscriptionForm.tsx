import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { formatUserDateTime } from "@/lib/date-time";

type Command = components["schemas"]["SubscriptionCommand"];

export function MemberSubscriptionForm({ account, tiers, onSaved }: {
  account: components["schemas"]["QuotaAccountOut"];
  tiers: components["schemas"]["QuotaTierOut"][];
  onSaved: () => void;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [action, setAction] = useState<Command["action"]>(account.subscriptionStatus === "ACTIVE" ? "RENEW" : "ACTIVATE");
  const [tierId, setTierId] = useState("");
  const [cycles, setCycles] = useState("1");
  const [reason, setReason] = useState("");
  const [key, setKey] = useState(() => crypto.randomUUID());
  const mutation = useMutation({
    mutationFn: () => unwrap(api.POST("/api/admin/quota-accounts/{user_id}/subscription", {
      params: { path: { user_id: account.userId } },
      body: { action, tierId: action === "ACTIVATE" ? tierId : null,
        cycles: action === "REVOKE" ? 1 : Number(cycles), reason: reason.trim(), idempotencyKey: key },
    })),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["admin"] });
      void queryClient.invalidateQueries({ queryKey: ["account"] });
      onSaved();
    },
  });
  const validCycles = Number.isInteger(Number(cycles)) && Number(cycles) >= 1 && Number(cycles) <= 52;
  const selectClass = "h-9 w-full rounded-md border bg-background px-3 text-sm";

  return (
    <section className="space-y-3 rounded-lg border p-4" aria-labelledby="subscription-heading">
      <h3 id="subscription-heading" className="font-semibold">{t("subscription.title")}</h3>
      <p className="text-xs text-muted-foreground">{t("subscription.help")}</p>
      {account.subscriptionStatus ? (
        <p className="text-sm">{t(`subscription.status.${account.subscriptionStatus}`)}
          {account.subscriptionExpiresAt ? ` · ${formatUserDateTime(account.subscriptionExpiresAt)}` : ""}
        </p>
      ) : <p className="text-sm text-muted-foreground">{t("subscription.unmanaged")}</p>}
      <fieldset disabled={mutation.isPending} className="space-y-3" onChange={() => setKey(crypto.randomUUID())}>
        <div className="space-y-1">
          <Label htmlFor="subscription-action">{t("subscription.action")}</Label>
          <select id="subscription-action" className={selectClass} value={action} onChange={(event) => setAction(event.target.value as Command["action"])}>
            <option value="ACTIVATE" disabled={account.subscriptionStatus === "ACTIVE"}>{t("subscription.activate")}</option>
            <option value="RENEW" disabled={!account.subscriptionStatus}>{t("subscription.renew")}</option>
            <option value="REVOKE" disabled={account.subscriptionStatus !== "ACTIVE"}>{t("subscription.revoke")}</option>
          </select>
        </div>
        {action === "ACTIVATE" ? (
          <div className="space-y-1">
            <Label htmlFor="subscription-tier">{t("subscription.plan")}</Label>
            <select id="subscription-tier" className={selectClass} value={tierId} onChange={(event) => setTierId(event.target.value)}>
              <option value="">{t("subscription.choosePlan")}</option>
              {tiers.filter((tier) => !tier.isDefault && !tier.archivedAt).map((tier) => (
                <option key={tier.id} value={tier.id}>{tier.name}</option>
              ))}
            </select>
          </div>
        ) : null}
        {action !== "REVOKE" ? (
          <div className="space-y-1">
            <Label htmlFor="subscription-cycles">{t("subscription.cycles")}</Label>
            <Input id="subscription-cycles" type="number" min={1} max={52} step={1} value={cycles} onChange={(event) => setCycles(event.target.value)} />
          </div>
        ) : <p className="text-xs text-muted-foreground">{t("subscription.revokeHelp")}</p>}
        <div className="space-y-1">
          <Label htmlFor="subscription-reason">{t("subscription.reason")}</Label>
          <Input id="subscription-reason" maxLength={500} value={reason} onChange={(event) => setReason(event.target.value)} />
        </div>
        <Button type="button" size="sm" disabled={!reason.trim() || (action === "ACTIVATE" && !tierId) || (action !== "REVOKE" && !validCycles)} onClick={() => mutation.mutate()}>
          {mutation.isPending ? t("subscription.saving") : t("subscription.save")}
        </Button>
      </fieldset>
      {mutation.isError ? <Alert variant="destructive"><AlertDescription>{mutation.error.message}</AlertDescription></Alert> : null}
    </section>
  );
}
