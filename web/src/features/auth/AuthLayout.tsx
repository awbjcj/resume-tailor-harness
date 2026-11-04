import type { ReactNode } from "react";
import { Fingerprint, GitBranch } from "lucide-react";
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
  description?: string;
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
          </div>
        </div>
        <LanguageSwitcher />
      </header>
      <main className="auth-main">
        <section className="auth-brand-story" data-slot="auth-brand-story" aria-label={t("auth.evidenceLedOperations")}>
          <div className="auth-brand-copy" data-slot="auth-brand-copy">
            <p className="auth-headline">{t("auth.brandHeadline")}<span>{t("auth.brandHeadlineAccent")}</span></p>
            <p className="auth-summary">{t("auth.brandSummary")}</p>
          </div>
        </section>
        <div className="auth-form-layer">
          <Card className="auth-card">
            <CardHeader className="auth-card-header">
              <div className="auth-card-title">
                <div className="auth-form-icon" aria-hidden="true">{icon ?? <Fingerprint />}</div>
                <h1>{title}</h1>
              </div>
              {description ? <p className="auth-description">{description}</p> : null}
            </CardHeader>
            <CardContent className="auth-card-content">
              {children}
              {footer ? <div className="auth-card-footer">{footer}</div> : null}
            </CardContent>
          </Card>
        </div>
      </main>
    </div>
  );
}
