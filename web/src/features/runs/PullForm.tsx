import { useId, useState } from "react";
import { Button } from "@/components/ui/button";
import { DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { launchers, useLaunchRun } from "./use-launch-run";

export default function PullForm({ onStarted }: { onStarted: () => void }) {
  const [limit, setLimit] = useState("");
  const id = useId();
  const { launch } = useLaunchRun();
  return <DialogContent>
    <DialogHeader>
      <DialogTitle>Pull from connectors</DialogTitle>
      <DialogDescription>Fetch and import job postings from every enabled connector.</DialogDescription>
    </DialogHeader>
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>Limit per connector (optional)</Label>
      <Input id={id} type="number" min={1} value={limit} onChange={(event) => setLimit(event.target.value)} placeholder="no limit" />
      <p className="text-xs text-muted-foreground">Maximum postings to fetch per connector for this run. Leave blank for no limit.</p>
    </div>
    <Button onClick={async () => {
      const parsed = Number(limit);
      const ok = await launch("pull", () => launchers.pull({ limit: limit && parsed > 0 ? parsed : null }));
      if (ok) onStarted();
    }}>Start pull</Button>
  </DialogContent>;
}
