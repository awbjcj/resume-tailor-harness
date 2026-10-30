import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Mail, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { useMailboxes } from "./use-mailboxes";
import { MailboxConnectionForm } from "./MailboxConnectionForm";
import { mailboxErrorMessage } from "./mailbox-errors";

export function MailboxConnections() {
  const { t, i18n } = useTranslation();
  const { query, connect, microsoft, disconnect, sync, isRunning, syncingAccountId } = useMailboxes();
  const [showForm, setShowForm] = useState(false);
  const addRef = useRef<HTMLButtonElement>(null);
  const errorRef = useRef<HTMLDivElement>(null);
  const restoreFocus = useRef(false);
  const busy = connect.isPending || microsoft.isPending || disconnect.isPending || sync.isPending || isRunning;
  const error = microsoft.error || disconnect.error || sync.error;
  useEffect(() => { if (error) errorRef.current?.focus(); }, [error]);
  useEffect(() => {
    if (!showForm && restoreFocus.current) {
      addRef.current?.focus();
      restoreFocus.current = false;
    }
  }, [showForm]);
  const closeForm = () => { restoreFocus.current = true; setShowForm(false); };
  const resetErrors = () => { connect.reset(); microsoft.reset(); disconnect.reset(); sync.reset(); };
  return (
    <section aria-labelledby="mailboxes-title" className="flex min-w-0 flex-col gap-4 rounded-lg border p-4">
      <header>
        <h2 id="mailboxes-title" className="flex items-center gap-2 text-base font-semibold"><Mail className="size-4" aria-hidden="true" />{t("mailboxes.title")}</h2>
        <p className="mt-1 text-sm text-muted-foreground">{t("mailboxes.help")}</p>
      </header>
      {query.isPending ? <Skeleton className="h-24" aria-label={t("mailboxes.loading")} /> : query.isError ? (
        <Alert variant="destructive"><AlertDescription>{t("mailboxes.loadError")}<Button variant="outline" onClick={() => void query.refetch()}>{t("mailboxes.retry")}</Button></AlertDescription></Alert>
      ) : <>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" disabled={busy || !query.data.providers.find((p) => p.id === "microsoft")?.available} onClick={() => { resetErrors(); microsoft.mutate(); }}>{t("mailboxes.microsoft")}</Button>
          <Button ref={addRef} variant="outline" disabled={showForm} onClick={() => { resetErrors(); setShowForm(true); }}>{t("mailboxes.add")}</Button>
        </div>
        {!query.data.providers.find((p) => p.id === "microsoft")?.available && <p className="text-sm text-muted-foreground">{t("mailboxes.microsoftUnavailable")}</p>}
        {query.data.accounts.length === 0 && !showForm && <p className="text-sm text-muted-foreground">{t("mailboxes.empty")}</p>}
        {query.data.accounts.map((account) => (
          <article key={account.id} className="flex min-w-0 flex-col gap-3 border-t pt-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
              <h3 className="break-all text-sm font-medium">{account.email}</h3>
              <p className="text-sm text-muted-foreground">{account.provider === "custom" ? t("mailboxes.custom") : query.data.providers.find((p) => p.id === account.provider)?.name}</p>
              <p className="text-sm text-muted-foreground">{t(account.needsReconnect ? "mailboxes.needsReconnect" : "mailboxes.status", { folder: account.folder })}</p>
              {account.smtpConfigured && <p className="text-sm text-muted-foreground">{t("mailboxes.smtpStatus")}</p>}
            </div>
            <div className="flex shrink-0 flex-wrap gap-2">
              {account.provider === "microsoft" && account.needsReconnect ? <Button variant="outline" disabled={busy} onClick={() => { resetErrors(); microsoft.mutate(); }}>{t("mailboxes.reconnect")}</Button> :
                <Button variant="outline" disabled={busy} onClick={() => { resetErrors(); sync.mutate(account.id); }}><RefreshCw className="size-4" aria-hidden="true" />{t((isRunning && syncingAccountId === account.id) || (sync.isPending && sync.variables === account.id) ? "mailboxes.syncing" : "mailboxes.sync")}</Button>}
              <Button variant="ghost" disabled={busy} onClick={() => { resetErrors(); disconnect.mutate(account.id, { onSuccess: () => addRef.current?.focus() }); }}>{t("mailboxes.disconnect")}</Button>
            </div>
          </article>
        ))}
        {showForm && <MailboxConnectionForm providers={query.data.providers} isSaving={connect.isPending} blocked={isRunning || microsoft.isPending || disconnect.isPending || sync.isPending} error={connect.error} onCancel={() => { resetErrors(); closeForm(); }} onSave={async (body) => { resetErrors(); if (await connect.submit(body)) closeForm(); }} />}
      </>}
      {error && <Alert ref={errorRef} tabIndex={-1} variant="destructive" className="scroll-mt-24"><AlertDescription>{mailboxErrorMessage(error, t, i18n.language)}</AlertDescription></Alert>}
    </section>
  );
}
