import { Dialog } from "@/components/ui/dialog";
import { DeferredDialogBody } from "@/components/DeferredDialogBody";

const load = () => import("./EmailDraftForm");

export function EmailDraftDialog({ jobId, defaultType, open, onOpenChange }: {
  jobId: number; defaultType?: string; open: boolean; onOpenChange: (open: boolean) => void;
}) {
  return <Dialog open={open} onOpenChange={onOpenChange}>
    <DeferredDialogBody active={open} title="Draft email" load={load} bodyProps={{ jobId, defaultType, open }} />
  </Dialog>;
}
