import { toast } from "sonner";

import i18n from "@/i18n";
import { api, unwrap } from "@/lib/api/client";

/** Resolve current workspace state only when the user opens a completed result. */
export async function openRunResult(runId: string, navigate = (href: string) => window.location.assign(href)) {
  try {
    const result = await unwrap(api.GET("/api/run-completions/by-run/{run_id}", {
      params: { path: { run_id: runId } },
    }));
    if (!result.resultHref) return;
    if (!result.resultAvailable) toast.info(i18n.t("runHistory.resultUnavailable"));
    navigate(result.resultHref);
  } catch {
    toast.error(i18n.t("runHistory.resultError"));
  }
}
