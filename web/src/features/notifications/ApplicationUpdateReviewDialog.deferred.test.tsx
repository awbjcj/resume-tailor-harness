import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { changeLanguage } from "@/i18n";
import { ApplicationUpdateReviewDialog } from "./ApplicationUpdateReviewDialog";
import type { NotificationItem } from "./use-notifications";

const deferredImport = vi.hoisted(() => ({
  requested: vi.fn(),
  finish: undefined as (() => void) | undefined,
}));

vi.mock("./ApplicationUpdateReviewBody", async () => {
  deferredImport.requested();
  await new Promise<void>((resolve) => { deferredImport.finish = resolve; });
  return {
    ApplicationUpdateReviewBody: ({ item }: { item: NotificationItem }) => (
      <div role="dialog" aria-label={item.revision}>{item.evidence}</div>
    ),
  };
});

afterEach(async () => { await changeLanguage("en"); });

it("imports the review only on demand and freezes evidence before loading, with localized loading feedback", async () => {
  const item: NotificationItem = {
    id: 4, applicationId: 2, kind: "interview", proposedStatus: "interview",
    evidence: "Original interview evidence", messageId: "mailbox:account-a:provider-1",
    state: "pending", createdAt: "2026-11-02T12:00:00Z", revision: "review-1", jobId: 7,
  };
  const user = userEvent.setup();
  const { rerender } = render(<ApplicationUpdateReviewDialog item={item} />);
  expect(deferredImport.requested).not.toHaveBeenCalled();
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Add to timeline" }));
  expect(await screen.findByRole("status")).toHaveTextContent("Loading");
  await waitFor(() => expect(deferredImport.requested).toHaveBeenCalledOnce());

  rerender(<ApplicationUpdateReviewDialog item={{ ...item, revision: "review-2", evidence: "Changed evidence" }} />);
  await act(() => changeLanguage("zh-CN"));
  expect(screen.getByRole("status")).toHaveTextContent("正在加载");
  await act(async () => { deferredImport.finish?.(); });
  expect(await screen.findByRole("dialog", { name: "review-1" })).toHaveTextContent(item.evidence);
  expect(screen.queryByText("Changed evidence")).not.toBeInTheDocument();
});
