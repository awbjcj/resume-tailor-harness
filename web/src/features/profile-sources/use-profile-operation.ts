import { useState } from "react";
import { useActiveRun } from "@/features/runs/use-active-run";

/** Keep the report readable after the global progress bar retires its run. */
export function useProfileOperation(kind: string) {
  const live = useActiveRun(kind);
  const [lastSeen, setLastSeen] = useState(live);
  if (live && live !== lastSeen) setLastSeen(live);
  return live ?? lastSeen;
}
