import { useState } from "react";
import { FileUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { DeferredDialogBody } from "@/components/DeferredDialogBody";

const load = () => import("./ImportJobsForm");

export function ImportJobsDialog({ open, onOpenChange }: {
  open: boolean; onOpenChange: (open: boolean) => void;
}) {
  return <Dialog open={open} onOpenChange={onOpenChange}>
    <DeferredDialogBody active={open} title="Import jobs" load={load} bodyProps={{ onOpenChange }} />
  </Dialog>;
}

export function ImportJobsButton() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
        <FileUp data-icon="inline-start" />
        Import file…
      </Button>
      <ImportJobsDialog open={open} onOpenChange={setOpen} />
    </>
  );
}
