import { useEffect, useRef, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Eye, EyeOff } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { accountErrorKey, type AccountErrorKey, type ApplicationAccount } from "./password-manager-api";

export type AccountFields = { company: string; loginUrl: string; username: string; password: string };

export function PasswordManagerForm({ account, disabled, onSave, onCancel }: {
  account: ApplicationAccount | null;
  disabled: boolean;
  onSave: (fields: AccountFields) => Promise<void>;
  onCancel: () => void;
}) {
  const { t } = useTranslation();
  const passwordRef = useRef<HTMLInputElement>(null);
  const errorRef = useRef<HTMLDivElement>(null);
  const submitting = useRef(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<AccountErrorKey | "">("");
  const [showPassword, setShowPassword] = useState(false);
  const accountId = account?.id;
  const invalidField = error === "passwordManager.companyError" ? "company"
    : error === "passwordManager.urlError" ? "url"
    : error === "passwordManager.usernameError" ? "username" : null;

  useEffect(() => { if (accountId) passwordRef.current?.focus(); }, [accountId]);
  useEffect(() => { if (error) errorRef.current?.focus(); }, [error, saving]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting.current || disabled) return;
    submitting.current = true;
    setSaving(true);
    setError("");
    const form = event.currentTarget;
    const fields = new FormData(form);
    try {
      await onSave({
        company: String(fields.get("company") ?? "").trim(),
        loginUrl: String(fields.get("loginUrl") ?? "").trim(),
        username: String(fields.get("username") ?? "").trim(),
        password: passwordRef.current?.value ?? "",
      });
      form.reset();
    } catch (cause) {
      setError(accountErrorKey(cause));
    } finally {
      // Passwords stay in the input/request only, never React or query state.
      if (passwordRef.current) passwordRef.current.value = "";
      setShowPassword(false);
      submitting.current = false;
      setSaving(false);
    }
  }

  return (
    <form onSubmit={(event) => void submit(event)} aria-labelledby="account-form-title" className="space-y-4 border-t pt-6">
      <h2 id="account-form-title" className="font-semibold [overflow-wrap:anywhere]">
        {account ? t("passwordManager.editTitle", { company: account.company }) : t("passwordManager.add")}
      </h2>
      {account && <p className="text-sm text-muted-foreground [overflow-wrap:anywhere]">{account.username} · {account.origin}</p>}
      {error && (
        <Alert ref={errorRef} tabIndex={-1} variant="destructive" className="focus-visible:ring-2 focus-visible:ring-ring">
          <AlertDescription>
            {invalidField ? <a href={`#account-${invalidField}`}>{t(error)}</a> : t(error)}
          </AlertDescription>
        </Alert>
      )}
      <fieldset disabled={disabled || saving} className="space-y-4">
        <legend className="sr-only">{t("passwordManager.savedAccounts")}</legend>
        {!account && <>
          <div className="space-y-2">
            <label htmlFor="account-company" className="text-sm font-medium">{t("passwordManager.company")}</label>
            <Input id="account-company" name="company" required maxLength={200} autoComplete="organization" aria-invalid={invalidField === "company"} aria-describedby={invalidField === "company" ? "account-company-error" : undefined} className="min-h-11" />
            {invalidField === "company" && <p id="account-company-error" className="text-sm text-destructive">{t("passwordManager.companyError")}</p>}
          </div>
          <div className="space-y-2">
            <label htmlFor="account-url" className="text-sm font-medium">{t("passwordManager.loginUrl")}</label>
            <Input id="account-url" name="loginUrl" type="url" required maxLength={2048} pattern="https://.*" aria-invalid={invalidField === "url"} aria-describedby={invalidField === "url" ? "account-site-help account-url-error" : "account-site-help"} className="min-h-11" />
            <p id="account-site-help" className="text-sm text-muted-foreground">{t("passwordManager.siteHelp")}</p>
            {invalidField === "url" && <p id="account-url-error" className="text-sm text-destructive">{t("passwordManager.urlError")}</p>}
          </div>
          <div className="space-y-2">
            <label htmlFor="account-username" className="text-sm font-medium">{t("passwordManager.username")}</label>
            <Input id="account-username" name="username" required maxLength={320} autoComplete="username" aria-invalid={invalidField === "username"} aria-describedby={invalidField === "username" ? "account-username-error" : undefined} className="min-h-11" />
            {invalidField === "username" && <p id="account-username-error" className="text-sm text-destructive">{t("passwordManager.usernameError")}</p>}
          </div>
        </>}
        <div className="space-y-2">
          <label htmlFor="account-password" className="text-sm font-medium">{t(account ? "passwordManager.newPassword" : "passwordManager.password")}</label>
          <div className="relative">
            <Input ref={passwordRef} id="account-password" type={showPassword ? "text" : "password"} required maxLength={1024} autoComplete="new-password" aria-describedby={account ? "account-password-help" : undefined} className="min-h-11 pr-12" />
            <Button type="button" variant="ghost" size="icon-lg" className="absolute inset-y-0 right-0" aria-label={t(showPassword ? "passwordManager.hidePassword" : "passwordManager.showPassword")} aria-pressed={showPassword} onClick={() => setShowPassword(!showPassword)}>
              {showPassword ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}
            </Button>
          </div>
          {account && <p id="account-password-help" className="text-sm text-muted-foreground">{t("passwordManager.updateHelp")}</p>}
        </div>
        <div className="flex flex-wrap gap-2">
          <Button type="submit" className="min-h-11">{t(saving ? "passwordManager.saving" : account ? "passwordManager.savePassword" : "passwordManager.save")}</Button>
          {account && <Button type="button" variant="outline" className="min-h-11" onClick={onCancel}>{t("passwordManager.cancel")}</Button>}
        </div>
      </fieldset>
    </form>
  );
}
