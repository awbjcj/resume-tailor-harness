import { useQuery } from "@tanstack/react-query";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader } from "@/components/PageHeader";
import { useMe } from "@/features/auth/AuthGate";
import { api, unwrap } from "@/lib/api/client";
import { AccountUsageCard } from "./AccountUsageCard";
import { BillingCard } from "./BillingCard";
import { DataArchiveCard } from "./DataArchiveCard";
import { DangerZoneCard } from "./DangerZoneCard";
import { PasswordCard } from "./PasswordCard";
import { PersonalTokensCard } from "./PersonalTokensCard";
import { SecurityCard } from "./SecurityCard";

export function AccountPage() {
  const me = useMe();
  const usage = useQuery({
    queryKey: ["account", "usage"],
    queryFn: () => unwrap(api.GET("/api/account/usage")),
  });

  if (!me.data || usage.isPending) return <Skeleton className="h-80 w-full" />;
  if (usage.isError || !usage.data) {
    return (
      <Alert variant="destructive">
        <AlertTitle>Account details are unavailable</AlertTitle>
        <AlertDescription>{usage.error?.message ?? "Please try again."}</AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        title="Account"
        meta={<>{me.data.username ? <span>{me.data.username}</span> : null}<Badge variant="outline">{me.data.role ?? "user"}</Badge></>}
      />

      {me.data.authRequired && me.data.role !== "admin" ? <BillingCard quota={usage.data.quota} /> : null}
      <section aria-labelledby="account-security" className="flex flex-col gap-4">
        <div>
          <h2 id="account-security" className="text-lg font-semibold">
            Security and access
          </h2>
        </div>
        <div className="grid gap-6 xl:grid-cols-2">
          <AccountUsageCard usage={usage.data} isAdmin={me.data.role === "admin"} />
          <PasswordCard />
        </div>
        <PersonalTokensCard />
        <SecurityCard />
      </section>

      <section aria-labelledby="account-data" className="flex flex-col gap-4">
        <div>
          <h2 id="account-data" className="text-lg font-semibold">
            Workspace data
          </h2>
        </div>
        <DataArchiveCard
          title="My workspace data"
          description="Export or replace the data in your workspace."
          exportLabel="Export my data"
          exportPath="/api/account/export"
          importPath="/api/account/import"
          successMessage="Workspace imported"
        />
        <DangerZoneCard />
      </section>
    </div>
  );
}
