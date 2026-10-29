import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";

import { GmailCard } from "../GmailCard";
import { SecretsForm } from "../forms/SecretsForm";
import { useGmailConnectOutcome } from "../use-gmail";
import { useSaveSecrets, useSecrets } from "../use-secrets";
import { EmailNotificationsPage } from "./EmailNotificationsPage";

export function EmailSettingsPage() {
  const secrets = useSecrets();
  const saveSecrets = useSaveSecrets();
  useGmailConnectOutcome();

  return (
    <div className="flex min-w-0 flex-col gap-8">
      <header className="space-y-1">
        <h1 className="text-lg font-semibold">Email & notifications</h1>
        <p className="text-sm text-muted-foreground">
          Connect Gmail, sync application updates, and choose the email notifications you receive.
        </p>
      </header>
      <div className="flex min-w-0 flex-col gap-4">
        <GmailCard />
        <details className="rounded-lg border px-4">
          <summary className="min-h-11 cursor-pointer rounded-md py-3 text-sm font-medium outline-none focus-visible:ring-2 focus-visible:ring-ring">
            Custom Gmail OAuth client (optional)
          </summary>
          <div className="flex flex-col gap-4 pb-4 pt-1">
            <p className="text-sm text-muted-foreground">
              Leave these fields empty to use the platform Gmail connection. Add your own Google OAuth client only if you need a custom connection.
            </p>
            {secrets.isError ? (
              <Alert variant="destructive">
                <AlertDescription>
                  <p>Could not load Gmail client settings.</p>
                  <Button variant="outline" onClick={() => void secrets.refetch()}>Retry</Button>
                </AlertDescription>
              </Alert>
            ) : secrets.data ? (
              <SecretsForm
                statuses={secrets.data.filter((secret) =>
                  secret.key === "googleOauthClientId" || secret.key === "googleOauthClientSecret",
                )}
                saving={saveSecrets.isPending}
                onSave={(patch) => saveSecrets.mutate(patch)}
              />
            ) : (
              <Skeleton className="h-24 w-full" aria-label="Loading Gmail client settings" />
            )}
          </div>
        </details>
      </div>
      <Separator />
      <section aria-label="Email notifications">
        <EmailNotificationsPage embedded />
      </section>
    </div>
  );
}
