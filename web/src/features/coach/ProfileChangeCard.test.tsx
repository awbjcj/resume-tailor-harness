import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { changeLanguage } from "@/i18n";
import { ProfileChangeCard } from "./ProfileChangeCard";
import type { CoachChangeDraft } from "./use-coach";

const draft: CoachChangeDraft = {
  id: "draft1", title: "Change headline", status: "pending", revision: "a".repeat(64),
  quotes: ["Set my headline to Backend Engineer"],
  previews: [{ label: "Update profile", entity: "profile", operation: "update",
    before: { contact: { headline: "Engineer", id: "internal-id" } },
    after: { contact: { headline: "Backend Engineer" } } }],
};

describe("ProfileChangeCard", () => {
  it("shows the exact change and request, and applies only on an explicit click", async () => {
    const resolve = vi.fn();
    render(<ProfileChangeCard draft={draft} busy={false} onResolve={resolve} />);
    expect(screen.getByText("Engineer")).toBeInTheDocument();
    expect(screen.getByText("Backend Engineer")).toBeInTheDocument();
    expect(screen.getByText(draft.quotes![0])).toBeInTheDocument();
    expect(screen.queryByText("internal-id")).not.toBeInTheDocument();
    expect(resolve).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Apply changes" }));
    expect(resolve).toHaveBeenCalledExactlyOnceWith("apply");
  });

  it("blocks actions while another turn or approval is running", () => {
    render(<ProfileChangeCard draft={draft} busy onResolve={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Apply changes" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Discard" })).toBeDisabled();
  });

  it("offers discard and hides all decisions once applied", async () => {
    const resolve = vi.fn();
    const { rerender } = render(<ProfileChangeCard draft={draft} busy={false} onResolve={resolve} />);
    await userEvent.click(screen.getByRole("button", { name: "Discard" }));
    expect(resolve).toHaveBeenCalledWith("discard");
    rerender(<ProfileChangeCard draft={{ ...draft, status: "applied" }} busy={false} onResolve={resolve} />);
    expect(screen.getByText("Applied")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("localizes the decision and field labels without translating user values", async () => {
    await changeLanguage("zh-CN");
    render(<ProfileChangeCard draft={draft} busy={false} onResolve={vi.fn()} />);
    expect(screen.getByRole("button", { name: "应用更改" })).toBeInTheDocument();
    expect(screen.getByText("更改前")).toBeInTheDocument();
    expect(screen.getAllByText("个人标题")).toHaveLength(2);
    expect(screen.getByText("Backend Engineer")).toBeInTheDocument();
  });
});
