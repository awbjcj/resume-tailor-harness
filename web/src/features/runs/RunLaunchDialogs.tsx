import { useState } from "react";
import { Dialog, DialogTrigger } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { DeferredDialogBody } from "@/components/DeferredDialogBody";
import { launchers, useLaunchRun } from "./use-launch-run";

const loadPull = () => import("./PullForm");
const loadReprocess = () => import("./ReprocessForm");

export function PullDialog({ triggerLabel = "Pull" }: { triggerLabel?: string } = {}) {
  const [open, setOpen] = useState(false);
  return <Dialog open={open} onOpenChange={setOpen}>
    <DialogTrigger render={<Button size="sm">{triggerLabel}</Button>} />
    <DeferredDialogBody active={open} title="Pull from connectors" load={loadPull} bodyProps={{ onStarted: () => setOpen(false) }} />
  </Dialog>;
}

export function DiscoverDialog() {
  const { launch } = useLaunchRun();
  return (
    <Button
      size="sm"
      variant="outline"
      onClick={() => launch("discover", () => launchers.discover())}
    >
      Discover
    </Button>
  );
}

export function RefreshButton() {
  const { launch } = useLaunchRun();
  return (
    <Button size="sm" variant="outline" onClick={() => launch("refresh", () => launchers.refresh())}>
      Refresh
    </Button>
  );
}


export function ReprocessDialog() {
  const [open, setOpen] = useState(false);
  return <Dialog open={open} onOpenChange={setOpen}>
    <DialogTrigger render={<Button size="sm" variant="outline">Reprocess</Button>} />
    <DeferredDialogBody active={open} title="Reprocess" load={loadReprocess} bodyProps={{ onStarted: () => setOpen(false) }} />
  </Dialog>;
}
