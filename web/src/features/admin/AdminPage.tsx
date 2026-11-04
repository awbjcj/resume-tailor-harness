import { ShieldCheck } from "lucide-react";
import { Navigate } from "react-router-dom";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader } from "@/components/PageHeader";
import { DataArchiveCard } from "@/features/account/DataArchiveCard";
import { useMe } from "@/features/auth/AuthGate";
import { AdminInviteCard } from "./AdminInviteCard";
import { AdminLimitsCard } from "./AdminLimitsCard";
import { AdminSectionNav } from "./AdminSectionNav";
import { AdminUsersCard } from "./AdminUsersCard";
import { MailWarning } from "./MailWarning";

export function AdminPage() {
  const me = useMe();

  if (me.isPending) return <Skeleton className="h-80 w-full" />;
  if (me.data?.role !== "admin") return <Navigate to="/" replace />;

  return (
    <div className="flex flex-col gap-8">
      <PageHeader title="Administration" />
      <AdminSectionNav current="/admin" />
      <Alert>
        <ShieldCheck aria-hidden="true" />
        <AlertTitle>Administrators are exempt from individual limits</AlertTitle>
        <AlertDescription>
          Cost allowances, active-job caps, and maximum concurrency do not apply to
          administrators. Their shared-key spend still counts against the platform cap.
        </AlertDescription>
      </Alert>
      <MailWarning />

      <section aria-labelledby="admin-controls" className="flex flex-col gap-4">
        <h2 id="admin-controls" className="text-lg font-semibold">Access and capacity</h2>
        <div className="grid gap-6 xl:grid-cols-[minmax(0,0.8fr)_minmax(0,1.4fr)]">
          <AdminInviteCard />
          <AdminLimitsCard />
        </div>
      </section>

      <DataArchiveCard
        title="System backup"
        description="Export or replace the complete server data root, including every workspace."
        exportLabel="Export all data"
        exportPath="/api/admin/export"
        importPath="/api/admin/import"
        successMessage="Data imported"
      />
      <AdminUsersCard currentUsername={me.data.username ?? ""} />
    </div>
  );
}
