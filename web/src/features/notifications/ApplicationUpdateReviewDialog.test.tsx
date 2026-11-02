import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { changeLanguage } from "@/i18n";
import { server } from "@/test/server";
import { withQueryClient } from "@/test/utils";
import { ApplicationUpdateReviewDialog } from "./ApplicationUpdateReviewDialog";
import type { NotificationItem } from "./use-notifications";

const item: NotificationItem = {
  id: 4, applicationId: 2, kind: "interview", proposedStatus: "interview",
  evidence: "Please choose a technical interview slot.",
  messageId: "mailbox:account-a:provider-1", state: "pending",
  createdAt: "2026-11-02T12:00:00Z", revision: "review-1",
  jobId: 7, company: "Acme", title: "Engineer",
};

describe("ApplicationUpdateReviewDialog", () => {
  afterEach(async () => { await changeLanguage("en"); });

  it("prefills evidence and status but requires the missing stage, date, time, timezone and confirmation", async () => {
    let accepted: unknown;
    server.use(http.post("*/api/notifications/4/accept", async ({ request }) => {
      accepted = await request.json();
      return HttpResponse.json({ ...item, state: "accepted" });
    }));
    const user = userEvent.setup();
    render(<ApplicationUpdateReviewDialog item={item} />, { wrapper: withQueryClient });
    await user.click(screen.getByRole("button", { name: "Add to timeline" }));
    expect(await screen.findByLabelText(/^stage$/i)).toHaveValue("");
    expect(screen.getByLabelText(/^date$/i)).toHaveValue("");
    expect(screen.getByLabelText(/^notes$/i)).toHaveValue(item.evidence);
    expect(screen.getByText("Proposed status: Interview")).toBeInTheDocument();
    expect(screen.getByText(/receipt time does not establish an interview appointment/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Accept and add event" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Choose the stage described in the message.");
    await user.selectOptions(screen.getByLabelText(/^stage$/i), "technical_round");
    await user.type(screen.getByLabelText(/^date$/i), "2026-11-06");
    await user.click(screen.getByRole("checkbox", { name: /^all day$/i }));
    expect(screen.getByLabelText(/^time$/i)).toHaveValue("");
    expect(screen.getByLabelText(/^timezone$/i)).toHaveValue("");
    await user.click(screen.getByRole("button", { name: "Accept and add event" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Enter the confirmed time and timezone");
    await user.type(screen.getByLabelText(/^time$/i), "14:00");
    await user.type(screen.getByLabelText(/^timezone$/i), "America/New_York");
    await user.click(screen.getByRole("button", { name: "Accept and add event" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Confirm the event details");
    expect(accepted).toBeUndefined();
    await user.click(screen.getByRole("checkbox", { name: /I confirmed the stage/ }));
    await user.click(screen.getByRole("button", { name: "Accept and add event" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(accepted).toEqual(expect.objectContaining({
      expectedRevision: "review-1", eventDetailsConfirmed: true,
      event: expect.objectContaining({
        kind: "technical_round", occurredAt: "2026-11-06T19:00:00.000Z",
        timezone: "America/New_York", allDay: false, notes: item.evidence,
      }),
    }));
  });

  it("keeps the reviewed revision and draft when the pending proposal changes during review", async () => {
    let accepted: { expectedRevision: string } | undefined;
    server.use(http.post("*/api/notifications/4/accept", async ({ request }) => {
      accepted = await request.json() as { expectedRevision: string };
      return HttpResponse.json({ error: { code: "NOTIFICATION_CHANGED", message: "Changed" } }, { status: 409 });
    }));
    const user = userEvent.setup();
    const { rerender } = render(<ApplicationUpdateReviewDialog item={item} />, { wrapper: withQueryClient });
    await user.click(screen.getByRole("button", { name: "Add to timeline" }));
    await user.selectOptions(await screen.findByLabelText(/^stage$/i), "online_assessment");
    await user.type(screen.getByLabelText(/^date$/i), "2026-11-06");
    await user.click(screen.getByRole("checkbox", { name: /I confirmed the stage/ }));
    rerender(<ApplicationUpdateReviewDialog item={{ ...item, revision: "review-2", evidence: "Corrected evidence" }} />);
    expect(screen.getByLabelText(/^notes$/i)).toHaveValue(item.evidence);
    expect(screen.queryByText("Corrected evidence")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Accept and add event" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Close this draft and review the latest application update.");
    expect(accepted?.expectedRevision).toBe("review-1");
    expect(screen.getByLabelText(/^date$/i)).toHaveValue("2026-11-06");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("localizes the review and confirmation in Simplified Chinese", async () => {
    await changeLanguage("zh-CN");
    const user = userEvent.setup();
    render(<ApplicationUpdateReviewDialog item={item} />, { wrapper: withQueryClient });
    await user.click(screen.getByRole("button", { name: "添加到时间线" }));
    expect(screen.getByRole("dialog", { name: "审核申请状态更新" })).toBeInTheDocument();
    expect(await screen.findByText("建议状态：面试中")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: /我已根据邮件或与雇主核实/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "接受并添加事件" })).toBeInTheDocument();
  });
});
