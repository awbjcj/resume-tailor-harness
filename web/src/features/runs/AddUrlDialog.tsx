import { useState } from "react";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogTrigger } from "@/components/ui/dialog";
import { DeferredDialogBody } from "@/components/DeferredDialogBody";

const load = () => import("./AddUrlForm");

export function AddUrlDialog() {
  const [open, setOpen] = useState(false);
  return <Dialog open={open} onOpenChange={setOpen}>
    <DialogTrigger render={<Button variant="outline" size="sm" />}>
      <Plus data-icon="inline-start" aria-hidden="true" /> Add job URL
    </DialogTrigger>
    <DeferredDialogBody active={open} title="Add job by URL" load={load} bodyProps={{ open }} />
  </Dialog>;
}
