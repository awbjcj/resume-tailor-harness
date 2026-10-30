import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { api, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { watchRun } from "@/lib/runs/sse";
import { useRunStore } from "@/lib/runs/store";

export type MailboxInput = components["schemas"]["MailboxConnectIn"];
export type MailProvider = components["schemas"]["MailProviderOut"];
const KEY = ["mailboxes"];

export function useMailboxes() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const outcome = params.get("mailbox");
  useEffect(() => {
    if (!outcome) return;
    if (outcome === "connected") {
      toast.success(t("mailboxes.connected"));
      void qc.invalidateQueries({ queryKey: KEY });
    } else {
      toast.error(t(outcome === "denied" ? "mailboxes.cancelled" : outcome === "invalid" ? "mailboxes.invalid" : "mailboxes.oauthError"));
    }
    setParams((current) => {
      const next = new URLSearchParams(current);
      next.delete("mailbox");
      return next;
    }, { replace: true });
  }, [outcome, qc, setParams, t]);
  const query = useQuery({ queryKey: KEY, queryFn: () => unwrap(api.GET("/api/mailboxes")) });
  // Connection credentials belong only to the form and its in-flight request.
  // useMutation retains variables in its cache even after the form unmounts.
  const [connection, setConnection] = useState<{ isPending: boolean; error: Error | null }>({ isPending: false, error: null });
  const connecting = useRef(false);
  const connect = {
    ...connection,
    reset: () => setConnection({ isPending: false, error: null }),
    submit: async (body: MailboxInput): Promise<boolean> => {
      if (connecting.current) return false;
      connecting.current = true;
      setConnection({ isPending: true, error: null });
      try {
        await unwrap(api.POST("/api/mailboxes", { body }));
        void qc.invalidateQueries({ queryKey: KEY });
        toast.success(t("mailboxes.connected"));
        setConnection({ isPending: false, error: null });
        return true;
      } catch (error) {
        setConnection({ isPending: false, error: error instanceof Error ? error : new Error(t("mailboxes.error")) });
        return false;
      } finally {
        connecting.current = false;
      }
    },
  };
  const microsoft = useMutation({
    mutationFn: async () => {
      const result = await unwrap(api.GET("/api/mailboxes/microsoft/connect"));
      window.location.assign(result.authUrl);
    },
  });
  const disconnect = useMutation({
    mutationFn: (accountId: string) => unwrap(api.DELETE("/api/mailboxes/{account_id}", { params: { path: { account_id: accountId } } })),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: KEY });
      toast.success(t("mailboxes.removed"));
    },
  });
  // Subscribe to identity only: progress events should not rerender the form.
  const syncingAccountId = useRunStore((state) => {
    const active = Object.values(state.runs).find(
      (run) => ["mailboxSync", "gmailSync"].includes(run.kind) && ["queued", "running", "cancelling"].includes(run.status),
    );
    if (!active) return null;
    return typeof active.meta?.accountId === "string" ? active.meta.accountId : "";
  });
  const sync = useMutation({
    mutationFn: (accountId: string) => unwrap(api.POST("/api/mailboxes/{account_id}/sync", { params: { path: { account_id: accountId } } })),
    onSuccess: (run, accountId) => {
      useRunStore.getState().upsert({
        runId: run.runId, kind: "mailboxSync", status: "running", percent: 0,
        phase: "", current: 0, total: 0, etaText: null, meta: { accountId },
      });
      watchRun(run.runId, "mailboxSync", () => {
        void qc.invalidateQueries({ queryKey: KEY });
        void qc.invalidateQueries({ queryKey: ["notifications"] });
      });
    },
  });
  return { query, connect, microsoft, disconnect, sync, isRunning: syncingAccountId !== null, syncingAccountId };
}
