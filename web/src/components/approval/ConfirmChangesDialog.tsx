import { useRef, type ReactNode } from "react";
import { AlertTriangle, Loader2 } from "lucide-react";

import { AlertDialog, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";

export function ConfirmChangesDialog({ open, onOpenChange, title, description, confirmLabel, cancelLabel, busy, disabled, error, onConfirm, finalFocus, children }: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  confirmLabel: string;
  cancelLabel: string;
  busy: boolean;
  disabled?: boolean;
  error?: ReactNode;
  onConfirm: () => void;
  finalFocus: () => HTMLElement | null;
  children: ReactNode;
}) {
  const cancelRef = useRef<HTMLButtonElement>(null);
  return (
    <AlertDialog open={open} onOpenChange={(next) => { if (!busy) onOpenChange(next); }}>
      <AlertDialogContent initialFocus={cancelRef} finalFocus={finalFocus} className="max-h-[90dvh] overflow-y-auto transition-none">
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription>{description}</AlertDialogDescription>
        </AlertDialogHeader>
        {children}
        {error ? <p role="alert" className="text-sm leading-relaxed text-destructive [overflow-wrap:anywhere]">{error}</p> : null}
        <AlertDialogFooter>
          <AlertDialogCancel ref={cancelRef} disabled={busy} className="h-auto min-h-11 whitespace-normal">{cancelLabel}</AlertDialogCancel>
          <Button variant="destructive" className="h-auto min-h-11 whitespace-normal" disabled={busy || disabled} onClick={onConfirm}>
            {busy ? <Loader2 className="motion-safe:animate-spin" aria-hidden="true" /> : <AlertTriangle aria-hidden="true" />}
            {confirmLabel}
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
