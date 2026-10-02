import { useEffect, useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Clock3, ExternalLink, LoaderCircle, LockKeyhole, Wallet } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api, unwrap } from "@/lib/api/client";
import { formatUserDateTime } from "@/lib/date-time";
import type { components } from "@/lib/api/schema";
import { billingRedirect } from "./billing-redirect";
import { BillingOfferCard } from "./BillingOfferCard";

export function BillingCard({ quota }: { quota?: components["schemas"]["QuotaSnapshotOut"] | null }) {
  const { t, i18n } = useTranslation();
  const client = useQueryClient();
  const [params] = useSearchParams();
  const sessionId = params.get("session_id");
  const isReturn = params.get("billing") === "success" && !!sessionId;
  const purchaseKeys = useRef(new Map<string, string>());
  const catalog = useQuery({
    queryKey: ["account", "billing"],
    queryFn: () => unwrap(api.GET("/api/account/billing")),
  });
  const status = useQuery({
    queryKey: ["account", "billing-checkout", sessionId],
    queryFn: () => unwrap(api.GET("/api/account/billing/checkout/{session_id}", { params: { path: { session_id: sessionId! } } })),
    enabled: isReturn && catalog.data?.enabled === true,
    retry: false,
    refetchInterval: (query) => !query.state.error && query.state.dataUpdateCount < 24 && ["pending", "open"].includes(query.state.data?.status ?? "") ? 2_500 : false,
  });
  useEffect(() => {
    if (status.data?.status === "fulfilled") {
      void client.invalidateQueries({ queryKey: ["account", "usage"] });
      void client.invalidateQueries({ queryKey: ["account", "billing"] });
    }
  }, [client, status.data?.status]);

  const checkout = useMutation({
    mutationFn: async (priceId: string) => {
      let key = purchaseKeys.current.get(priceId);
      if (!key) {
        key = crypto.randomUUID();
        purchaseKeys.current.set(priceId, key);
      }
      const result = await api.POST("/api/account/billing/checkout", { body: { priceId, idempotencyKey: key } });
      const failure = result.error as { error?: { code?: string } } | undefined;
      if (failure?.error?.code === "BILLING_CHECKOUT_ENDED") purchaseKeys.current.delete(priceId);
      return unwrap(Promise.resolve(result));
    },
    onSuccess: (result) => billingRedirect(result.url),
  });
  const portal = useMutation({
    mutationFn: () => unwrap(api.POST("/api/account/billing/portal")),
    onSuccess: (result) => billingRedirect(result.url),
  });
  if (catalog.isPending) return <div aria-busy="true" aria-label={t("billing.loading")} className="grid gap-4"><Skeleton className="h-32 w-full" /><div className="grid gap-4 md:grid-cols-2"><Skeleton className="h-80 w-full" /><Skeleton className="h-80 w-full" /></div></div>;
  if (catalog.data?.enabled === false) return null;
  const money = (cents: number) => new Intl.NumberFormat(i18n.language, { style: "currency", currency: "USD" }).format(cents / 100);
  const subscription = catalog.data?.subscription;
  const subscribed = !!subscription && !["canceled", "incomplete_expired"].includes(subscription.status);
  const busy = checkout.isPending || portal.isPending;
  const error = catalog.error || checkout.error || portal.error || status.error;
  const confirmed = status.data?.status === "fulfilled";
  const expired = status.data?.status === "expired";
  const offers = catalog.data?.offers ?? [];
  const creditOffers = offers.filter((offer) => offer.mode === "payment");
  const planOffers = offers.filter((offer) => offer.mode === "subscription");
  const managed = subscribed || quota?.subscriptionStatus === "ACTIVE";
  const renderOffer = (offer: components["schemas"]["BillingOffer"]) => <BillingOfferCard key={offer.priceId} offer={offer} money={money} disabled={busy} loading={checkout.isPending && checkout.variables === offer.priceId} managed={managed} current={offer.mode === "subscription" && managed && quota?.tierId === offer.tierId} onPurchase={(priceId) => checkout.mutate(priceId)} />;

  return (
    <section aria-labelledby="account-billing">
    <Card className="[--card-spacing:--spacing(5)] sm:[--card-spacing:--spacing(6)]">
      <CardHeader className="gap-2 border-b">
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-primary"><Wallet className="size-4" aria-hidden="true" />{t("billing.kicker")}</div>
        <CardTitle><h2 id="account-billing" className="text-xl font-semibold tracking-tight sm:text-2xl">{t("billing.title")}</h2></CardTitle>
        <CardDescription className="max-w-[65ch] leading-6">{t("billing.description")}</CardDescription>
        {catalog.data?.portalAvailable ? <CardAction><Button variant="outline" className="min-h-11 cursor-pointer" disabled={busy} aria-busy={portal.isPending} onClick={() => portal.mutate()}>{t(portal.isPending ? "billing.openingPortal" : "billing.manage")}{portal.isPending ? <LoaderCircle aria-hidden="true" className="animate-spin motion-reduce:animate-none" /> : <ExternalLink aria-hidden="true" />}</Button></CardAction> : null}
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        {quota ? <dl className="grid gap-5 rounded-lg bg-muted/35 p-4 sm:grid-cols-3 sm:gap-6 sm:p-5">
          <div className="min-w-0"><dt className="text-xs font-medium text-muted-foreground">{t("billing.planLabel")}</dt><dd className="mt-1.5 break-words text-lg font-semibold">{quota.tierName}</dd></div>
          <div className="min-w-0"><dt className="text-xs font-medium text-muted-foreground">{t("billing.balanceLabel")}</dt><dd className="mt-1.5 text-2xl font-semibold tracking-tight tabular-nums">{money(quota.creditBalanceMicros / 10_000)}</dd></div>
          <div className="min-w-0"><dt className="text-xs font-medium text-muted-foreground">{t("billing.allowanceLabel")}</dt><dd className="mt-1.5 text-2xl font-semibold tracking-tight tabular-nums">{quota.recurringAllowanceMicros == null ? t("billing.unlimitedLabel") : money(quota.recurringAllowanceMicros / 10_000)}</dd></div>
        </dl> : null}
        {error ? <Alert variant="destructive" role="alert"><AlertTitle>{t("billing.error")}</AlertTitle><AlertDescription className="flex flex-col items-start gap-3">{error.message}<Button variant="outline" className="min-h-11 cursor-pointer" onClick={() => { void catalog.refetch(); if (isReturn) void status.refetch(); }}>{t("billing.refresh")}</Button></AlertDescription></Alert> : null}
        {isReturn && !status.isError ? <Alert role="status" aria-live="polite" aria-atomic="true" className="tone-panel" data-tone={confirmed ? "success" : expired ? "warning" : "info"}>{confirmed ? <CheckCircle2 aria-hidden="true" /> : <Clock3 aria-hidden="true" />}<AlertTitle>{t(confirmed ? "billing.received" : expired ? "billing.expired" : "billing.processing")}</AlertTitle><AlertDescription className="flex flex-col items-start gap-3">{t(confirmed ? "billing.receivedHelp" : expired ? "billing.expiredHelp" : "billing.processingHelp")}{!confirmed && !expired ? <Button variant="outline" className="min-h-11 cursor-pointer" disabled={status.isFetching} onClick={() => { void status.refetch(); }}>{t("billing.refresh")}</Button> : null}</AlertDescription></Alert> : null}
        {params.get("billing") === "canceled" ? <p role="status" className="text-sm leading-6 text-muted-foreground">{t("billing.canceled")}</p> : null}
        {subscription ? <div className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border px-4 py-3 text-sm"><Badge variant="outline">{t(`billing.status.${subscription.status}`, { defaultValue: subscription.status })}</Badge>{subscription.paidThrough ? <span className="text-muted-foreground">{t(subscription.cancelAtPeriodEnd ? "billing.ends" : "billing.paidThrough", { date: formatUserDateTime(subscription.paidThrough) })}</span> : null}</div> : null}
        <div className="grid items-start gap-6 md:grid-cols-2">
          {creditOffers.length ? <div className="flex min-w-0 flex-col gap-4"><div><h3 className="text-base font-semibold">{t("billing.creditSection")}</h3><p className="mt-1 text-sm leading-6 text-muted-foreground">{t("billing.creditSectionHelp")}</p></div>{creditOffers.map(renderOffer)}</div> : null}
          {planOffers.length ? <div className="flex min-w-0 flex-col gap-4"><div><h3 className="text-base font-semibold">{t("billing.planSection")}</h3><p className="mt-1 text-sm leading-6 text-muted-foreground">{t("billing.planSectionHelp")}</p></div>{planOffers.map(renderOffer)}</div> : null}
        </div>
        {offers.length === 0 && !catalog.isError ? <p className="text-sm text-muted-foreground">{t("billing.noOffers")}</p> : null}
      </CardContent>
      <CardFooter className="items-start gap-2.5 bg-muted/25"><LockKeyhole aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-muted-foreground" /><p className="max-w-[90ch] text-xs leading-5 text-muted-foreground">{t("billing.note")}</p></CardFooter>
    </Card>
    </section>
  );
}
