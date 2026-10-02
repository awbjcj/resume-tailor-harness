import type { ReactNode } from "react";
import { ArrowRight, FileCheck2, ShieldCheck } from "lucide-react";
import { useTranslation } from "react-i18next";

import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { Card, CardContent, CardHeader } from "@/components/ui/card";

export function AuthLayout({
  title,
  description,
  icon,
  children,
  footer,
}: {
  title: string;
  description: string;
  icon?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
}) {
  const { t } = useTranslation();
  return (
    <div className="auth-shell flex min-h-svh bg-background">
      <aside
        data-slot="auth-brand"
        aria-hidden="true"
        className="auth-brand-panel"
      >
        <div className="auth-brand-header">
          <div className="auth-brand-mark">
            <FileCheck2 className="size-5" aria-hidden="true" />
          </div>
          <div>
            <p className="text-sm font-semibold tracking-tight">Résumé Tailor Harness</p>
            <p className="auth-brand-subtitle">{t("auth.privateCareerWorkspace")}</p>
          </div>
        </div>

        <div data-slot="auth-brand-story" className="auth-brand-story">
          <div data-slot="auth-brand-copy" className="auth-brand-copy">
            <p className="auth-brand-eyebrow">
              <span />{t("auth.evidenceLedOperations")}
            </p>
            <h2 className="auth-brand-copy-heading">
              {t("auth.brandHeadline")}<br />
              <em>{t("auth.brandHeadlineAccent")}</em>
            </h2>
            <p className="auth-brand-copy-summary">{t("auth.brandSummary")}</p>
          </div>
        </div>

        <div data-slot="auth-brand-visual" className="auth-brand-workflow">
          <div className="auth-workflow-labels">
            <span>{t("auth.sourceRecords")}</span>
            <span>{t("auth.tailoredResume")}</span>
            <span>{t("auth.validation")}</span>
          </div>
          <div className="auth-brand-artwork" />
        </div>

        <div className="auth-brand-footer">
          <div className="auth-brand-steps">
            <span><small>01</small>{t("auth.discover")}</span>
            <span><small>02</small>{t("auth.tailor")}</span>
            <span><small>03</small>{t("auth.track")}</span>
            <ArrowRight className="size-5 shrink-0" aria-hidden="true" />
          </div>
          <p>{t("auth.brandPromise")}</p>
        </div>
      </aside>
      <main className="auth-surface relative flex min-h-svh w-full items-center justify-center px-5 pb-8 pt-24 sm:px-10 sm:pb-12 sm:pt-24">
        <div className="absolute right-4 top-4 sm:right-8 sm:top-6">
          <LanguageSwitcher />
        </div>
        <div className="w-full max-w-[28rem]">
          <div className="mb-6 flex items-center gap-3 px-1 lg:hidden">
            <div className="flex size-10 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-[0_10px_28px_-14px_color-mix(in_oklab,var(--primary),transparent_28%)]">
              <FileCheck2 className="size-4.5" aria-hidden="true" />
            </div>
            <div>
              <div className="text-sm font-semibold leading-tight tracking-tight">Résumé Tailor Harness</div>
              <div className="mt-0.5 text-[0.68rem] font-medium uppercase tracking-[0.18em] text-muted-foreground">
                {t("auth.privateCareerWorkspace")}
              </div>
            </div>
          </div>
          <Card className="auth-card w-full gap-0 rounded-2xl py-0 shadow-card-raised ring-foreground/9">
            <CardHeader className="gap-0 px-6 pb-5 pt-6 sm:px-7 sm:pt-7">
              <div className="mb-5 flex items-center justify-between gap-3">
                {icon ? (
                  <div className="flex size-11 items-center justify-center rounded-xl border border-primary/15 bg-accent text-accent-foreground shadow-[inset_0_1px_0_color-mix(in_oklab,var(--background),transparent_18%)] [&_svg]:size-5">
                    {icon}
                  </div>
                ) : <span />}
                <div className="flex items-center gap-1.5 rounded-full border border-border/80 bg-muted/55 px-2.5 py-1 text-[0.68rem] font-medium text-muted-foreground">
                  <ShieldCheck className="size-3.5 text-primary" aria-hidden="true" />
                  {t("auth.secureWorkspace")}
                </div>
              </div>
              <h1 className="text-[1.75rem] font-semibold leading-tight tracking-[-0.03em]">{title}</h1>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{description}</p>
            </CardHeader>
            <CardContent className="px-6 pb-6 sm:px-7 sm:pb-7">
              {children}
              {footer ? <div className="mt-6 border-t border-border/70 pt-5 text-sm">{footer}</div> : null}
            </CardContent>
          </Card>
          <p className="mt-5 px-2 text-center text-xs leading-relaxed text-muted-foreground">
            {t("auth.sourceMaterialPromise")}
          </p>
        </div>
      </main>
    </div>
  );
}
