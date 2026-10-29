import { Mail, RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { localizeRunError } from "@/i18n/dynamic-labels";
import { useGmailSync } from "@/features/notifications/use-notifications";
import {
  useGmailConnect,
  useGmailDisconnect,
  useGmailStatus,
} from "./use-gmail";

export function GmailCard() {
  const { i18n } = useTranslation();
  const { data: status, isLoading, isError, refetch } = useGmailStatus();
  const connect = useGmailConnect();
  const disconnect = useGmailDisconnect();
  const sync = useGmailSync();

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
              disabled={connect.isPending || disconnect.isPending || sync.isPending}
              onClick={() => connect.mutate()}
            >
              Reconnect
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={disconnect.isPending || connect.isPending || sync.isPending}
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
          Sync recruiting emails to suggest application updates. Review changes in Notifications before applying them.
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
      {sync.error && (
        <p role="alert" className="text-sm text-destructive">
          {localizeRunError(sync.error.message, i18n.resolvedLanguage)}
        </p>
      )}
    </section>
  );
}
