import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { QueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { api, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import type { RunRecord } from "@/lib/runs/store";
import { useRunStore } from "@/lib/runs/store";
import { trackRun } from "@/lib/runs/tracker";

export type ScoutSession = components["schemas"]["ScoutSessionOut"];
export type ScoutSessionSummary = components["schemas"]["ScoutSessionSummaryOut"];
export type ScoutSessions = components["schemas"]["ScoutSessionsOut"];
export type ScoutProposal = components["schemas"]["ScoutProposalOut"];
type RunOut = components["schemas"]["RunOut"];
type RunDone = (run: RunRecord) => void;

const proposalDecisions = new WeakMap<QueryClient, Set<string>>();

/** Inline cards and the ledger can target the same proposal before React has
 * rendered the pending state. Admit only one decision per proposal at a time. */
async function decideProposal<T>(client: QueryClient, sessionId: string, proposalId: string, action: () => Promise<T>): Promise<T> {
  let pending = proposalDecisions.get(client);
  if (!pending) { pending = new Set(); proposalDecisions.set(client, pending); }
  const key = `${sessionId}:${proposalId}`;
  if (pending.has(key)) throw new Error("A decision for this proposal is already in progress.");
  pending.add(key);
  try { return await action(); } finally { pending.delete(key); }
}

const listKey = (archived: boolean) => ["scout-sessions", archived] as const;
const detailKey = (id: string | null) => ["scout-session", id] as const;

function seedScoutRun(run: RunOut, onDone?: RunDone) {
  useRunStore.getState().upsert({
    runId: run.runId, kind: run.kind, status: "running", percent: run.percent,
    phase: run.label, current: run.current, total: run.total,
    etaText: run.etaText ?? null, meta: run.meta ?? null,
  });
  trackRun({ runId: run.runId, kind: run.kind }, onDone);
}

export function useScoutSessions(includeArchived = false) {
  return useQuery({
    queryKey: listKey(includeArchived),
    queryFn: () => unwrap(api.GET("/api/scout/sessions", { params: { query: includeArchived ? { includeArchived: true } : {} } })) as Promise<ScoutSessions>,
  });
}

export function useScoutSession(sessionId: string | null) {
  return useQuery({
    queryKey: detailKey(sessionId), enabled: Boolean(sessionId),
    queryFn: () => unwrap(api.GET("/api/scout/sessions/{session_id}", { params: { path: { session_id: sessionId as string } } })) as Promise<ScoutSession>,
  });
}

function useScoutInvalidation() {
  const client = useQueryClient();
  return () => Promise.all([
    client.invalidateQueries({ queryKey: ["scout-sessions"] }),
    client.invalidateQueries({ queryKey: ["scout-session"] }),
  ]);
}

function useScoutRun<T extends Record<string, unknown>>(launch: (input: T) => Promise<RunOut>) {
  const invalidate = useScoutInvalidation();
  return useMutation({
    mutationFn: async (input: T & { onDone?: RunDone }) => {
      const run = await launch(input);
      seedScoutRun(run, async (done) => { await invalidate(); input.onDone?.(done); });
      return run;
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

export function useStartScoutSession() {
  return useScoutRun(({ message }: { message: string }) => unwrap(api.POST("/api/scout/sessions", { body: { message } })));
}

export function useSendScoutMessage() {
  return useScoutRun(({ sessionId, message }: { sessionId: string; message: string }) =>
    unwrap(api.POST("/api/scout/sessions/{session_id}/messages", { params: { path: { session_id: sessionId } }, body: { message } })),
  );
}

export function useEndScoutSession() {
  return useScoutRun(({ sessionId }: { sessionId: string }) =>
    unwrap(api.POST("/api/scout/sessions/{session_id}/end", { params: { path: { session_id: sessionId } } })),
  );
}

export function useApproveScoutProposal() {
  const client = useQueryClient();
  return useMutation({
    mutationKey: ["scout-proposal-action"],
    mutationFn: ({ sessionId, proposalId, manualConfirmation = false }: { sessionId: string; proposalId: string; manualConfirmation?: boolean }) => {
      const params = { params: { path: { session_id: sessionId, proposal_id: proposalId } } };
      return decideProposal(client, sessionId, proposalId, () => manualConfirmation
        ? unwrap(api.POST("/api/scout/sessions/{session_id}/proposals/{proposal_id}/approve", { ...params, body: { manualConfirmation: true } }))
        : unwrap(api.POST("/api/scout/sessions/{session_id}/proposals/{proposal_id}/approve", params)));
    },
    onSuccess: () => Promise.all([
      client.invalidateQueries({ queryKey: ["scout-session"] }),
      client.invalidateQueries({ queryKey: ["scout-sessions"] }),
      client.invalidateQueries({ queryKey: ["sources"] }),
      client.invalidateQueries({ queryKey: ["config", "/api/config/search"] }),
    ]),
    onError: (error: Error) => toast.error(error.message),
  });
}

export function useResolveScoutProposal() {
  const client = useQueryClient();
  const invalidate = useScoutInvalidation();
  return useMutation({
    mutationKey: ["scout-proposal-action"],
    mutationFn: ({ sessionId, proposalId, url }: { sessionId: string; proposalId: string; url: string }) =>
      decideProposal(client, sessionId, proposalId, () => unwrap(api.POST("/api/scout/sessions/{session_id}/proposals/{proposal_id}/resolve", {
        params: { path: { session_id: sessionId, proposal_id: proposalId } },
        body: { url },
      }))),
    onSuccess: invalidate,
    onError: (error: Error) => toast.error(error.message),
  });
}

export function useDismissScoutProposal() {
  const client = useQueryClient();
  const invalidate = useScoutInvalidation();
  return useMutation({
    mutationKey: ["scout-proposal-action"],
    mutationFn: ({ sessionId, proposalId, reason }: { sessionId: string; proposalId: string; reason: string }) =>
      decideProposal(client, sessionId, proposalId, () => unwrap(api.POST("/api/scout/sessions/{session_id}/proposals/{proposal_id}/dismiss", { params: { path: { session_id: sessionId, proposal_id: proposalId } }, body: { reason } }))),
    onSuccess: invalidate, onError: (error: Error) => toast.error(error.message),
  });
}

function useLifecycle(action: "archive" | "unarchive" | "delete") {
  const invalidate = useScoutInvalidation();
  return useMutation({
    mutationFn: ({ sessionId }: { sessionId: string }) => {
      const params = { params: { path: { session_id: sessionId } } };
      if (action === "delete") return unwrap(api.DELETE("/api/scout/sessions/{session_id}", params));
      if (action === "archive") return unwrap(api.POST("/api/scout/sessions/{session_id}/archive", params));
      return unwrap(api.POST("/api/scout/sessions/{session_id}/unarchive", params));
    },
    onSuccess: invalidate, onError: (error: Error) => toast.error(error.message),
  });
}

export const useArchiveScoutSession = () => useLifecycle("archive");
export const useUnarchiveScoutSession = () => useLifecycle("unarchive");
export const useDeleteScoutSession = () => useLifecycle("delete");

export function useRenameScoutSession() {
  const invalidate = useScoutInvalidation();
  return useMutation({
    mutationFn: ({ sessionId, title }: { sessionId: string; title: string }) =>
      unwrap(api.PATCH("/api/scout/sessions/{session_id}", {
        params: { path: { session_id: sessionId } }, body: { title },
      })),
    onSuccess: invalidate,
    onError: (error: Error) => toast.error(error.message),
  });
}
