import { useId, useState } from "react";
import { Button } from "@/components/ui/button";
import { DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { launchers, useLaunchRun, type ReprocessScope } from "./use-launch-run";

const SCOPES: { value: ReprocessScope; label: string }[] = [
  { value: "shortlisted", label: "Re-score shortlist" },
  { value: "rejected:relevance", label: "Reconsider off-target" },
  { value: "rejected:filtered", label: "Reconsider hard-filtered" },
  { value: "all", label: "Everything (no progress)" },
];

export default function ReprocessForm({ onStarted }: { onStarted: () => void }) {
  const [scope, setScope] = useState<ReprocessScope>("shortlisted");
  const id = useId();
  const { launch } = useLaunchRun();
  return <DialogContent>
    <DialogHeader>
      <DialogTitle>Reprocess</DialogTitle>
      <DialogDescription>Re-run the full funnel for one scope. Fit scores and statuses may change. Jobs with progress are not changed.</DialogDescription>
    </DialogHeader>
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>Scope</Label>
      <Select items={SCOPES} value={scope} onValueChange={(value) => value && setScope(value as ReprocessScope)}>
        <SelectTrigger id={id} className="w-full"><SelectValue /></SelectTrigger>
        <SelectContent>{SCOPES.map((item) => <SelectItem key={item.value} value={item.value}>{item.label}</SelectItem>)}</SelectContent>
      </Select>
    </div>
    <Button onClick={async () => {
      const ok = await launch("reprocess", () => launchers.reprocess([scope]));
      if (ok) onStarted();
    }}>Start reprocess</Button>
  </DialogContent>;
}
