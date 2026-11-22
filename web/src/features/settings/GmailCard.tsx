import "@/i18n/interaction-copy-notifications";
import { Mail, RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { localizeRunError } from "@/i18n/dynamic-labels";
import { useGmailSync } from "@/features/notifications/use-notifications";
import {
  useGmailAutomation,
  useGmailConnect,
  useGmailDisconnect,
  useGmailStatus,
} from "./use-gmail";

export function GmailCard() {
  const { t, i18n } = useTranslation();
  const { data: status, isLoading, isError, refetch } = useGmailStatus();
  const connect = useGmailConnect();
  const disconnect = useGmailDisconnect();
  const sync = useGmailSync();
  const automation = useGmailAutomation();

  return (
    <section aria-labelledby="gmail-settings-title" className="flex flex-col gap-4 rounded-lg border p-4">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h2 id="gmail-settings-title" className="flex items-start gap-2 text-base font-semibold">
            <Mail className="mt-0.5 size-4 shrink-0" aria-hidden="true" /> Gmail connection & sync
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            {isError
              ? "Could not check Gmail. Try again; your connection may still be active."
              : isLoading
                ? "Checking connection…"
                : status?.connected
                  ? status.draftCapable
                    ? `Connected (${status.clientSource} client). Sync and drafts are enabled.`
                    : `Connected (${status.clientSource} client). Reconnect to enable drafts.`
                  : "Not connected. Connect to sync application status and draft emails."}
          </p>
        </div>
        {isError ? (
          <Button size="sm" variant="outline" onClick={() => void refetch()}>
            Retry
          </Button>
        ) : status?.connected ? (
          <div className="flex shrink-0 flex-wrap gap-2">
            <Button
              size="sm"
              variant="outline"
              disabled={connect.isPending || disconnect.isPending || sync.isPending || automation.isPending}
              onClick={() => connect.mutate()}
            >
              Reconnect
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={disconnect.isPending || connect.isPending || sync.isPending || automation.isPending}
              onClick={() => disconnect.mutate()}
            >
              Disconnect
            </Button>
          </div>
        ) : (
          <Button
            size="sm"
            className="self-start"
            disabled={connect.isPending || isLoading}
            onClick={() => connect.mutate()}
          >
            Connect Gmail
          </Button>
        )}
      </div>
      <div className="flex flex-col gap-3 border-t pt-4 sm:flex-row sm:items-center sm:justify-between">
        <p className="min-w-0 text-sm text-muted-foreground">
          {t("interactionCopy.notifications.gmailSettingsHelp")}
        </p>
        <Button
          className="shrink-0 self-start"
          variant="outline"
          disabled={!status?.connected || isError || sync.isPending || connect.isPending || disconnect.isPending}
          onClick={() => sync.mutate()}
        >
          <RefreshCw aria-hidden="true" className={sync.isPending ? "animate-spin motion-reduce:animate-none" : undefined} />
          {sync.isPending ? "Syncing…" : "Sync Gmail"}
        </Button>
      </div>
      {status?.connected && (
        <div className="flex items-start justify-between gap-4 border-t pt-4">
          <div>
            <label htmlFor="gmail-auto-rejections" className="text-sm font-medium">
              Auto-apply confirmed rejections
            </label>
            <p id="gmail-auto-rejections-help" className="mt-1 text-sm text-muted-foreground">
              Future emails with an authenticated employer, an exact requisition, and a clear rejection can move a Submitted application to Rejected. Each change appears on the application timeline.
            </p>
            {automation.error && (
              <p role="alert" className="mt-2 text-sm text-destructive">
                {localizeRunError(automation.error.message, i18n.resolvedLanguage)}
              </p>
            )}
          </div>
          <Switch
            id="gmail-auto-rejections"
            aria-describedby="gmail-auto-rejections-help"
            checked={status.autoApplyRejections ?? false}
            disabled={automation.isPending || disconnect.isPending || connect.isPending || isError}
            onCheckedChange={(enabled) => automation.mutate(enabled)}
          />
        </div>
      )}
      {sync.error && (
        <p role="alert" className="text-sm text-destructive">
          {localizeRunError(sync.error.message, i18n.resolvedLanguage)}
        </p>
      )}
    </section>
  );
}
