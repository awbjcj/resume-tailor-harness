import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";

export function ClearHistoryButton({ label, pending, disabled, error, onClear }: {
  label: string; pending: boolean; disabled: boolean; error: Error | null;
  onClear: (onSuccess: () => void) => void;
}) {
  const { t } = useTranslation();
  const [confirming, setConfirming] = useState(false);
  return <div className="space-y-2">
    {confirming ? <div className="flex flex-wrap items-center gap-2">
      <span className="text-xs text-muted-foreground">{t("runHistory.clearConfirm")}</span>
      <Button size="xs" variant="destructive" disabled={pending}
        onClick={() => onClear(() => setConfirming(false))}>{t("runHistory.confirmClear")}</Button>
      <Button size="xs" variant="ghost" disabled={pending}
        onClick={() => setConfirming(false)}>{t("runHistory.keepHistory")}</Button>
    </div> : <Button size="xs" variant="outline" disabled={disabled || pending}
      onClick={() => setConfirming(true)}>{label}</Button>}
    {error && <p role="alert" className="text-xs text-destructive">{t("runHistory.clearError")}</p>}
  </div>;
}
