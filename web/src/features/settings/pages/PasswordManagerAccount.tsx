import { useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { accountErrorKey, type AccountErrorKey, type ApplicationAccount } from "./password-manager-api";

export function PasswordManagerAccount({ account, disabled, removing, onEdit, onRemove }: {
  account: ApplicationAccount;
  disabled: boolean;
  removing: boolean;
  onEdit: (trigger: HTMLButtonElement) => void;
  onRemove: () => Promise<void>;
}) {
  const { t } = useTranslation();
  const id = useId();
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<AccountErrorKey | "">("");
  const cancelRef = useRef<HTMLButtonElement>(null);
  const removeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => { if (confirming) cancelRef.current?.focus(); }, [confirming]);

  function cancel() {
    setConfirming(false);
    setError("");
    removeRef.current?.focus();
  }

  return (
    <li className="min-w-0 space-y-3 rounded-lg border p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 space-y-1 [overflow-wrap:anywhere]">
          <h3 id={`${id}-title`} className="font-medium">{account.company}</h3>
          <p className="text-sm">{account.username}</p>
          <p className="text-sm text-muted-foreground">{account.origin}</p>
          <p className="text-sm font-medium">{t(`passwordManager.${account.status}`)}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" className="min-h-11" disabled={disabled} aria-describedby={`${id}-title`} onClick={(event) => onEdit(event.currentTarget)}>{t("passwordManager.edit")}</Button>
          <Button ref={removeRef} variant="ghost" className="min-h-11 text-destructive" disabled={disabled} aria-describedby={`${id}-title`} aria-expanded={confirming} aria-controls={confirming ? `${id}-confirmation` : undefined} onClick={() => setConfirming(true)}>{t("passwordManager.remove")}</Button>
        </div>
      </div>
      {confirming && (
        <div id={`${id}-confirmation`} className="space-y-3 border-t pt-3" onKeyDown={(event) => { if (event.key === "Escape" && !disabled) cancel(); }}>
          <p id={`${id}-description`} className="text-sm [overflow-wrap:anywhere]">{t("passwordManager.removeConfirm", { company: account.company })}</p>
          {error && <p role="alert" className="text-sm text-destructive">{t(error)}</p>}
          <div className="flex flex-wrap gap-2">
            <Button variant="destructive" className="min-h-11" disabled={disabled} aria-describedby={`${id}-description`} onClick={() => {
              setError("");
              void onRemove().catch((cause: unknown) => setError(accountErrorKey(cause)));
            }}>{t(removing ? "passwordManager.removing" : "passwordManager.confirmRemove")}</Button>
            <Button ref={cancelRef} variant="outline" className="min-h-11" disabled={disabled} onClick={cancel}>{t("passwordManager.cancel")}</Button>
          </div>
        </div>
      )}
    </li>
  );
}
