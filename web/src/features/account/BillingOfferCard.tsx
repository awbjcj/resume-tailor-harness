import { ArrowUpRight, Check, LoaderCircle } from "lucide-react";
import { useId } from "react";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { components } from "@/lib/api/schema";
import { cn } from "@/lib/utils";

type Offer = components["schemas"]["BillingOffer"];

export function BillingOfferCard({ offer, disabled, loading, managed, current, money, onPurchase }: {
  offer: Offer;
  disabled: boolean;
  loading: boolean;
  managed: boolean;
  current: boolean;
  money: (cents: number) => string;
  onPurchase: (priceId: string) => void;
}) {
  const { t } = useTranslation();
  const recurring = offer.mode === "subscription";
  const heading = useId();
  const action = loading ? "billing.opening" : !recurring ? "billing.addCredit" : managed ? "billing.currentPlan" : "billing.subscribe";

  return (
    <article aria-labelledby={heading} className={cn(
      "flex min-w-0 flex-col overflow-hidden rounded-xl border bg-card",
      recurring && "border-primary/30",
    )}>
      <div className={cn("flex flex-wrap items-center justify-between gap-2 border-b px-5 py-3", recurring ? "border-primary/20 bg-primary/5" : "bg-muted/35")}>
        <h4 id={heading} className="break-words text-base font-semibold">{recurring ? offer.name : t("billing.credits")}</h4>
        <Badge variant="outline" className={cn("shrink-0 bg-card", current && "border-primary/40 text-primary")}>
          {t(current ? "billing.current" : recurring ? "billing.recurring" : "billing.oneTime")}
        </Badge>
      </div>
      <div className="flex flex-1 flex-col gap-5 p-5 sm:p-6">
        <div>
          <p className="text-[clamp(1.75rem,3vw,2.25rem)] font-semibold leading-tight tracking-tight tabular-nums">{money(offer.amountCents)}</p>
          <p className="mt-1 text-sm text-muted-foreground">
            {offer.interval ? t(`billing.interval.${offer.interval}`, { count: offer.intervalCount ?? 1 }) : t("billing.payOnce")}
          </p>
        </div>
        <div className="border-t pt-4">
          <p className="text-sm font-medium leading-6">
            {!recurring ? t("billing.creditAmount", { amount: money((offer.creditMicros ?? 0) / 10_000) }) : offer.allowanceMicros == null ? t("billing.unlimited") : t("billing.allowance", { amount: money(offer.allowanceMicros / 10_000) })}
          </p>
          <ul className="mt-3 grid gap-2.5 text-sm leading-5 text-muted-foreground">
            {(recurring ? ["billing.renewalBenefit", "billing.cancelBenefit"] as const : ["billing.durableBenefit", "billing.creditOrderBenefit"] as const).map((key) => (
              <li key={key} className="flex items-start gap-2"><Check aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-primary" /><span>{t(key)}</span></li>
            ))}
          </ul>
        </div>
        <div className="mt-auto pt-1">
          <Button
            className="min-h-11 w-full cursor-pointer gap-2 transition-colors duration-150 motion-reduce:transition-none"
            variant={recurring ? "default" : "outline"}
            disabled={disabled || (recurring && managed)}
            aria-busy={loading}
            aria-label={loading || (recurring && managed) ? t(action) : recurring ? t("billing.subscribeTo", { plan: offer.name }) : t("billing.addCreditFor", { amount: money(offer.amountCents) })}
            onClick={() => onPurchase(offer.priceId)}
          >
            {t(action)}
            {loading ? <LoaderCircle aria-hidden="true" className="size-4 animate-spin motion-reduce:animate-none" /> : !managed || !recurring ? <ArrowUpRight aria-hidden="true" className="size-4" /> : null}
          </Button>
          <p className="mt-2.5 text-center text-xs leading-5 text-muted-foreground">{t(recurring ? "billing.autoRenew" : "billing.noSubscription")}</p>
        </div>
      </div>
    </article>
  );
}
