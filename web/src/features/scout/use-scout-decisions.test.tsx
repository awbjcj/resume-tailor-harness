import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { expect, it } from "vitest";
import { server } from "@/test/server";
import { withQueryClient } from "@/test/utils";
import { useApproveScoutProposal, useDismissScoutProposal } from "./use-scout";

it("prevents competing inline and ledger decisions from issuing duplicate requests", async () => {
  let finish!: () => void;
  const pending = new Promise<void>((resolve) => { finish = resolve; });
  let approvals = 0;
  let dismissals = 0;
  server.use(
    http.post("/api/scout/sessions/s/proposals/p/approve", async () => { approvals++; await pending; return HttpResponse.json({}); }),
    http.post("/api/scout/sessions/s/proposals/p/dismiss", () => { dismissals++; return HttpResponse.json({}); }),
  );
  const { result } = renderHook(() => ({ inline: useApproveScoutProposal(), ledger: useApproveScoutProposal(), dismiss: useDismissScoutProposal() }), { wrapper: withQueryClient });
  let first!: Promise<unknown>;
  act(() => { first = result.current.inline.mutateAsync({ sessionId: "s", proposalId: "p" }); });
  await waitFor(() => expect(approvals).toBe(1));
  await act(async () => {
    await expect(result.current.ledger.mutateAsync({ sessionId: "s", proposalId: "p" })).rejects.toThrow("already in progress");
    await expect(result.current.dismiss.mutateAsync({ sessionId: "s", proposalId: "p", reason: "No" })).rejects.toThrow("already in progress");
    finish(); await first;
  });
  expect(approvals).toBe(1);
  expect(dismissals).toBe(0);
});
