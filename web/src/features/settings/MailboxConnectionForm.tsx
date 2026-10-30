import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import type { MailboxInput, MailProvider } from "./use-mailboxes";
import { mailboxErrorFields, mailboxErrorMessage, mailboxFieldLabel } from "./mailbox-errors";

const selectClass = "h-11 w-full min-w-0 scroll-mt-24 rounded-md border bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";
type Server = MailboxInput["imap"];
const blankServer = (): Server => ({ host: "", port: 993, security: "tls", username: "", password: "" });
const fieldId = (path: string) => `mailbox-${path.replace(".", "-")}`;

function ServerFields({ kind, value, onChange, errors }: {
  kind: "imap" | "smtp"; value: Server; onChange: (server: Server) => void; errors: string[];
}) {
  const { t } = useTranslation();
  const accessibility = (field: string) => ({
    id: fieldId(`${kind}.${field}`),
    "aria-invalid": errors.includes(`${kind}.${field}`) || undefined,
    "aria-describedby": errors.includes(`${kind}.${field}`) ? `${fieldId(`${kind}.${field}`)}-error` : undefined,
  });
  const issue = (field: string) => errors.includes(`${kind}.${field}`) && (
    <p id={`${fieldId(`${kind}.${field}`)}-error`} className="text-sm text-destructive">{t("mailboxes.checkField")}</p>
  );
  return (
    <div className="grid min-w-0 gap-4 sm:grid-cols-2">
      <Field>
        <FieldLabel htmlFor={fieldId(`${kind}.host`)}>{t("mailboxes.host")}</FieldLabel>
        <Input {...accessibility("host")} required maxLength={253} autoCapitalize="none" spellCheck={false} value={value.host} onChange={(e) => onChange({ ...value, host: e.target.value })} />
        {issue("host")}
      </Field>
      <Field>
        <FieldLabel htmlFor={fieldId(`${kind}.port`)}>{t("mailboxes.port")}</FieldLabel>
        <Input {...accessibility("port")} type="number" required min={1} max={65535} value={value.port || ""} onChange={(e) => onChange({ ...value, port: Number(e.target.value) })} />
        {issue("port")}
      </Field>
      <Field>
        <FieldLabel htmlFor={fieldId(`${kind}.security`)}>{t("mailboxes.security")}</FieldLabel>
        <select {...accessibility("security")} className={selectClass} value={value.security} onChange={(e) => {
          const security = e.target.value as Server["security"];
          const ports = kind === "imap" ? { tls: 993, starttls: 143 } : { tls: 465, starttls: 587 };
          onChange({ ...value, security, port: value.port === ports[value.security ?? "tls"] ? ports[security ?? "tls"] : value.port });
        }}>
          <option value="tls">{t("mailboxes.tls")}</option>
          <option value="starttls">{t("mailboxes.starttls")}</option>
        </select>
        {issue("security")}
      </Field>
      <Field>
        <FieldLabel htmlFor={fieldId(`${kind}.username`)}>{t("mailboxes.username")}</FieldLabel>
        <Input {...accessibility("username")} required maxLength={254} autoComplete={`section-${kind} username`} autoCapitalize="none" spellCheck={false} value={value.username} onChange={(e) => onChange({ ...value, username: e.target.value })} />
        {issue("username")}
      </Field>
      <Field className="sm:col-span-2">
        <FieldLabel htmlFor={fieldId(`${kind}.password`)}>{t("mailboxes.password")}</FieldLabel>
        <Input {...accessibility("password")} type="password" required maxLength={4096} autoComplete={`section-${kind} current-password`} value={value.password} onChange={(e) => onChange({ ...value, password: e.target.value })} />
        {issue("password")}
      </Field>
    </div>
  );
}

export function MailboxConnectionForm({ providers, isSaving, blocked, error, onSave, onCancel }: {
  providers: MailProvider[]; isSaving: boolean; blocked: boolean; error: Error | null;
  onSave: (body: MailboxInput) => void; onCancel: () => void;
}) {
  const { t, i18n } = useTranslation();
  const [provider, setProvider] = useState<MailboxInput["provider"]>("custom");
  const [email, setEmail] = useState("");
  const [folder, setFolder] = useState("INBOX");
  const [imap, setImap] = useState<Server>(blankServer);
  const [smtp, setSmtp] = useState<Server>({ ...blankServer(), port: 465 });
  const [useSmtp, setUseSmtp] = useState(false);
  const providerRef = useRef<HTMLSelectElement>(null);
  const errorRef = useRef<HTMLDivElement>(null);
  useEffect(() => { providerRef.current?.focus(); }, []);
  useEffect(() => { if (error) errorRef.current?.focus(); }, [error]);
  const selected = providers.find((p) => p.id === provider);
  const errors = mailboxErrorFields(error);
  const errorText = error ? mailboxErrorMessage(error, t, i18n.language) : "";
  return (
    <form className="space-y-5 rounded-md border bg-muted/20 p-4 [&_input]:scroll-mt-24" aria-label={t("mailboxes.add")} aria-busy={isSaving} onSubmit={(event) => {
      event.preventDefault();
      if (!isSaving && !blocked) onSave({ provider, email, folder, imap, smtp: useSmtp ? smtp : null });
    }}>
      {error && <Alert ref={errorRef} tabIndex={-1} variant="destructive" className="scroll-mt-24 focus:outline-2 focus:outline-offset-2 focus:outline-ring" aria-labelledby="mailbox-error-title">
        <AlertDescription>
          <p id="mailbox-error-title" className="font-medium">{errorText}</p>
          {errors.length > 0 && <ul className="mt-2 list-inside list-disc">
            {errors.map((path) => <li key={path}><a href={`#${fieldId(path)}`} className="underline underline-offset-4" onClick={(event) => { event.preventDefault(); document.getElementById(fieldId(path))?.focus(); }}>
              {path.includes(".") ? `${t(path.startsWith("imap.") ? "mailboxes.imap" : "mailboxes.smtp")} · ` : ""}{mailboxFieldLabel(path, t)}
            </a></li>)}
          </ul>}
        </AlertDescription>
      </Alert>}
      <fieldset disabled={isSaving} className="min-w-0 space-y-5">
        <Field>
          <FieldLabel htmlFor="mailbox-provider">{t("mailboxes.provider")}</FieldLabel>
          <select ref={providerRef} id="mailbox-provider" className={selectClass} value={provider} aria-describedby="mailbox-provider-help" onChange={(e) => {
            const next = providers.find((p) => p.id === e.target.value);
            if (!next) return;
            setProvider(next.id as MailboxInput["provider"]);
            setImap({ ...blankServer(), username: email, host: next.imapHost ?? "" });
            setSmtp({ ...blankServer(), username: email, host: next.smtpHost ?? "", port: next.smtpPort ?? 465, security: next.smtpSecurity });
          }}>
            {providers.filter((p) => p.auth === "password").map((p) => <option key={p.id} value={p.id}>{p.id === "custom" ? t("mailboxes.custom") : p.name}</option>)}
          </select>
          <FieldDescription id="mailbox-provider-help">{t("mailboxes.passwordHelp")} {selected?.helpUrl && <a className="underline underline-offset-4" href={selected.helpUrl} target="_blank" rel="noreferrer">{t("mailboxes.helpLink")}</a>}</FieldDescription>
        </Field>
        <Field>
          <FieldLabel htmlFor="mailbox-email">{t("mailboxes.email")}</FieldLabel>
          <Input id="mailbox-email" required type="email" maxLength={254} autoComplete="email" aria-invalid={errors.includes("email") || undefined} aria-describedby={errors.includes("email") ? "mailbox-email-error" : undefined} value={email} onChange={(e) => {
            const value = e.target.value;
            if (!imap.username || imap.username === email) setImap({ ...imap, username: value });
            if (!smtp.username || smtp.username === email) setSmtp({ ...smtp, username: value });
            setEmail(value);
          }} />
          {errors.includes("email") && <p id="mailbox-email-error" className="text-sm text-destructive">{t("mailboxes.checkField")}</p>}
        </Field>
        <fieldset className="min-w-0 space-y-4"><legend className="mb-3 text-sm font-semibold">{t("mailboxes.imap")}</legend>
          <ServerFields kind="imap" value={imap} onChange={setImap} errors={errors} />
          <Field>
            <FieldLabel htmlFor="mailbox-folder">{t("mailboxes.folder")}</FieldLabel>
            <Input id="mailbox-folder" required maxLength={200} value={folder} onChange={(e) => setFolder(e.target.value)} aria-invalid={errors.includes("folder") || undefined} aria-describedby={errors.includes("folder") ? "mailbox-folder-help mailbox-folder-error" : "mailbox-folder-help"} />
            <FieldDescription id="mailbox-folder-help">{t("mailboxes.folderHelp")}</FieldDescription>
            {errors.includes("folder") && <p id="mailbox-folder-error" className="text-sm text-destructive">{t("mailboxes.checkField")}</p>}
          </Field>
        </fieldset>
        <div className="space-y-3 border-t pt-4">
          <label className="flex min-h-11 cursor-pointer items-center gap-3 text-sm font-medium">
            <input type="checkbox" checked={useSmtp} onChange={(e) => setUseSmtp(e.target.checked)} className="size-4" aria-describedby="mailbox-smtp-help" />
            {t("mailboxes.smtp")}
          </label>
          <p id="mailbox-smtp-help" className="text-sm text-muted-foreground">{t("mailboxes.smtpHelp")}</p>
          {useSmtp && <fieldset className="min-w-0"><legend className="sr-only">{t("mailboxes.smtp")}</legend><ServerFields kind="smtp" value={smtp} onChange={setSmtp} errors={errors} /></fieldset>}
        </div>
        {blocked && <p role="status" className="text-sm text-muted-foreground">{t("mailboxes.busy")}</p>}
        <div className="flex flex-wrap gap-2">
          <Button type="submit" disabled={blocked}>{t(isSaving ? "mailboxes.saving" : "mailboxes.save")}</Button>
          <Button type="button" variant="outline" onClick={onCancel}>{t("mailboxes.cancel")}</Button>
        </div>
      </fieldset>
    </form>
  );
}
