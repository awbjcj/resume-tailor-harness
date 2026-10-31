import type { ReactNode } from "react";
import { Fingerprint, GitBranch, ShieldCheck } from "lucide-react";
import { useTranslation } from "react-i18next";

import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { AuthWorkflowCanvas } from "./AuthWorkflowCanvas";
import "./auth.css";

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
    <div className="auth-shell dark">
      <AuthWorkflowCanvas />
      <header className="auth-header">
        <div className="auth-brand-header">
          <div className="auth-brand-mark"><GitBranch aria-hidden="true" /></div>
          <div className="min-w-0">
            <p className="auth-brand-name">{t("auth.brandName")} <span>{t("auth.brandSuffix")}</span></p>
            <p className="auth-brand-subtitle">{t("auth.privateCareerWorkspace")}</p>
          </div>
        </div>
        <LanguageSwitcher />
      </header>
      <main className="auth-main">
        <section className="auth-brand-story" data-slot="auth-brand-story" aria-label={t("auth.evidenceLedOperations")}>
          <div className="auth-brand-copy" data-slot="auth-brand-copy">
            <p className="auth-eyebrow"><span />{t("auth.evidenceLedOperations")}</p>
            <p className="auth-headline">{t("auth.brandHeadline")}<span>{t("auth.brandHeadlineAccent")}</span></p>
            <p className="auth-summary">{t("auth.brandSummary")}</p>
            <div className="auth-principles">
              <span><Fingerprint aria-hidden="true" />{t("auth.traceableEvidence")}</span>
              <span><ShieldCheck aria-hidden="true" />{t("auth.humanControl")}</span>
            </div>
          </div>
        </section>
        <div className="auth-form-layer">
          <Card className="auth-card">
            <CardHeader className="auth-card-header">
              <div className="auth-card-meta">
                <div className="auth-form-icon">{icon ?? <Fingerprint aria-hidden="true" />}</div>
                <span className="auth-secure-label"><ShieldCheck aria-hidden="true" />{t("auth.secureWorkspace")}</span>
              </div>
              <h1>{title}</h1>
              <p className="auth-description">{description}</p>
            </CardHeader>
            <CardContent className="auth-card-content">
              {children}
              {footer ? <div className="auth-card-footer">{footer}</div> : null}
            </CardContent>
          </Card>
          <p className="auth-form-note"><ShieldCheck aria-hidden="true" />{t("auth.sourceMaterialPromise")}</p>
        </div>
      </main>
      <footer className="auth-footer">
        <p>{t("auth.brandPromise")}</p>
        <span><span className="auth-footer-line" />{t("auth.workflowCaption")}</span>
      </footer>
    </div>
  );
}
