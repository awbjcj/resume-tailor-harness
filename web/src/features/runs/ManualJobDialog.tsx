import { useState } from "react";
import { useTranslation } from "react-i18next";
import { PenLine } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogTrigger } from "@/components/ui/dialog";
import { DeferredDialogBody } from "@/components/DeferredDialogBody";

const load = () => import("./ManualJobForm");

export function ManualJobDialog() {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  return <Dialog open={open} onOpenChange={(next) => { if (!busy) setOpen(next); }}>
    <DialogTrigger render={<Button size="sm" variant="outline" />}>
      <PenLine data-icon="inline-start" aria-hidden="true" />{t("manualJob.title")}
    </DialogTrigger>
    <DeferredDialogBody active={open} title={t("manualJob.title")} load={load}
      bodyProps={{ onClose: () => setOpen(false), onBusyChange: setBusy }} />
  </Dialog>;
}
