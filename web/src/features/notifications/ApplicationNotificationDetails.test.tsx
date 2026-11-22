import { act, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { changeLanguage } from "@/i18n";
import { ApplicationNotificationDetails } from "./ApplicationNotificationDetails";
import type { NotificationItem } from "./use-notifications";

const notification: NotificationItem = {
  id: 1, applicationId: 2, jobId: 3, kind: "other", proposedStatus: "",
  evidence: "Original message from the employer.", messageId: "message-1",
  state: "pending", revision: "r1", createdAt: "2026-10-23T12:00:00Z",
};

describe("ApplicationNotificationDetails", () => {
  it("labels an update without a proposed status and preserves its message", async () => {
    render(<ApplicationNotificationDetails item={notification} />);
    expect(screen.getByText("Application update")).toBeInTheDocument();

    await act(async () => { await changeLanguage("zh-CN"); });
    expect(screen.getByText("申请更新")).toBeInTheDocument();
    expect(screen.getByText("Original message from the employer.")).toBeInTheDocument();
  });
});
