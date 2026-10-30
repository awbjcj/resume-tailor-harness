import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { KeyRound, ShieldCheck } from "lucide-react";
import { toast } from "sonner";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { api, unwrap } from "@/lib/api/client";
import { PasswordManagerAccount } from "./PasswordManagerAccount";
import { PasswordManagerForm, type AccountFields } from "./PasswordManagerForm";
import { AccountError, accountErrorKey, accountRequest, type AccountErrorKey, type ApplicationAccount } from "./password-manager-api";

const queryKey = ["application-accounts"];

export function PasswordManagerPage() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const vault = useQuery({ queryKey, queryFn: () => unwrap(api.GET("/api/application-accounts")) });
  // Background refreshes must not silently authorize overwriting a new password.
  const [editing, setEditing] = useState<ApplicationAccount | null>(null);
  const [operation, setOperation] = useState<string | null>(null);
  const [policyError, setPolicyError] = useState<AccountErrorKey | "">("");
  const inFlight = useRef(false);
  const editTrigger = useRef<HTMLButtonElement | null>(null);
  const savedHeading = useRef<HTMLHeadingElement>(null);
  const accounts = vault.data?.accounts ?? [];
  const busy = operation !== null;

  async function mutate(kind: string, write: () => Promise<void>) {
    if (inFlight.current) throw new AccountError("passwordManager.busyError");
    inFlight.current = true;
    setOperation(kind);
    try {
      await qc.cancelQueries({ queryKey });
      await write();
    } catch (error) {
      const refreshed = await vault.refetch();
      // A conflict requires re-entry and an explicit retry with the new revision.
      // Keep deleted edits in edit mode so a retry cannot recreate an account.
      if (kind === "save" && editing && refreshed.data) {
        setEditing(refreshed.data.accounts?.find((a) => a.id === editing.id) ?? editing);
      }
      throw error;
    } finally {
      inFlight.current = false;
      setOperation(null);
    }
  }

  async function changePolicy(enabled: boolean) {
    if (!vault.data) return;
    const revision = vault.data.revision;
    setPolicyError("");
    try {
      await mutate("policy", async () => {
        const saved = await accountRequest(api.PATCH("/api/application-accounts/policy", {
          body: { autoRegister: enabled, revision, userConfirmed: true },
        }));
        qc.setQueryData(queryKey, saved);
        toast.success(t("passwordManager.policySaved"));
      });
    } catch (error) {
      setPolicyError(accountErrorKey(error));
    }
  }

  async function save(fields: AccountFields) {
    await mutate("save", async () => {
      if (editing) {
        await accountRequest(api.PATCH("/api/application-accounts/{account_id}", {
          params: { path: { account_id: editing.id } },
          body: { password: fields.password, revision: editing.revision, userConfirmed: true },
        }));
      } else {
        await accountRequest(api.POST("/api/application-accounts", { body: { ...fields, userConfirmed: true } }));
      }
      setEditing(null);
      toast.success(t("passwordManager.saved"));
      await qc.invalidateQueries({ queryKey });
      savedHeading.current?.focus();
    });
  }

  async function remove(account: ApplicationAccount) {
    await mutate(account.id, async () => {
      await accountRequest(api.DELETE("/api/application-accounts/{account_id}", {
        params: { path: { account_id: account.id }, query: { revision: account.revision } },
      }));
      if (editing?.id === account.id) setEditing(null);
      toast.success(t("passwordManager.removed"));
      await qc.invalidateQueries({ queryKey });
      savedHeading.current?.focus();
    });
  }

  return (
    <div className="flex min-w-0 max-w-3xl flex-col gap-7">
      <header className="space-y-2">
        <h1 className="flex items-center gap-2 text-xl font-semibold"><KeyRound aria-hidden="true" className="size-5 shrink-0" />{t("passwordManager.title")}</h1>
        <p className="text-sm text-muted-foreground">{t("passwordManager.description")}</p>
      </header>
      {vault.isPending && <p role="status">{t("passwordManager.loading")}</p>}
      {vault.isError && (
        <Alert variant="destructive"><AlertDescription>
          {t("passwordManager.loadError")}
          <Button variant="outline" disabled={vault.isFetching} onClick={() => void vault.refetch()}>{t("passwordManager.retry")}</Button>
        </AlertDescription></Alert>
      )}
      {vault.data && !vault.data.configured && <Alert><AlertDescription>{t("passwordManager.unavailable")}</AlertDescription></Alert>}
      {vault.data?.configured && <>
        <div className="space-y-3 rounded-lg border p-4">
          <div className="flex items-start justify-between gap-4">
            <div className="space-y-2">
              <label htmlFor="auto-register" className="font-medium">{t("passwordManager.autoRegister")}</label>
              <p id="auto-register-help" className="text-sm text-muted-foreground">{t("passwordManager.autoHelp")}</p>
            </div>
            <Switch id="auto-register" aria-describedby="auto-register-help" checked={vault.data.autoRegister} disabled={busy} onCheckedChange={(enabled) => void changePolicy(enabled)} />
          </div>
          {operation === "policy" && <p role="status" className="text-sm text-muted-foreground">{t("passwordManager.saving")}</p>}
          {policyError && <p role="alert" className="text-sm text-destructive">{t(policyError)}</p>}
        </div>
        <p className="flex items-start gap-2 text-sm text-muted-foreground"><ShieldCheck aria-hidden="true" className="mt-0.5 size-4 shrink-0" />{t("passwordManager.storageHelp")}</p>
        <section aria-labelledby="saved-accounts" className="space-y-3">
          <h2 ref={savedHeading} id="saved-accounts" tabIndex={-1} className="font-semibold focus-visible:outline-2 focus-visible:outline-ring">{t("passwordManager.savedAccounts")}</h2>
          {!accounts.length && <p className="rounded-lg border border-dashed p-5 text-sm text-muted-foreground">{t("passwordManager.empty")}</p>}
          <ul className="space-y-3">
            {accounts.map((account) => (
              <PasswordManagerAccount key={account.id} account={account} disabled={busy} removing={operation === account.id} onRemove={() => remove(account)} onEdit={(trigger) => {
                editTrigger.current = trigger;
                setEditing(account);
              }} />
            ))}
          </ul>
        </section>
        <PasswordManagerForm key={editing?.id ?? "new"} account={editing} disabled={busy} onSave={save} onCancel={() => {
          setEditing(null);
          editTrigger.current?.focus();
        }} />
      </>}
    </div>
  );
}
