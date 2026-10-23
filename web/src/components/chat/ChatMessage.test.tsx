import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { ChatMessage } from "./ChatMessage";
import { changeLanguage } from "@/i18n";

describe("ChatMessage", () => {
  it("renders known tool names, statuses, and empty results in Chinese", async () => {
    await changeLanguage("zh-CN");
    render(<ChatMessage showReasoning message={{ id: "zh-tool", role: "assistant", parts: [{
      kind: "tool", callId: "tool-zh", name: "web_search", argsPreview: "Acme",
      resultPreview: "No result was returned.", ok: false, done: true,
    }] }} />);
    expect(screen.getByText("助手")).toBeInTheDocument();
    expect(screen.getByText("网页搜索")).toBeInTheDocument();
    expect(screen.getByText("失败")).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: /网页搜索/ }));
    expect(screen.getByText("未返回结果。")).toBeVisible();
  });
  it("renders streamed citations as safe external links", () => {
    render(<ChatMessage showReasoning message={{ id: "sources", role: "assistant", parts: [{ kind: "sources", items: [{ url: "https://example.com/source", title: "Official source" }] }] }} />);
    const link = screen.getByRole("link", { name: "Official source" });
    expect(link).toHaveAttribute("href", "https://example.com/source");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("renders a named assistant and structured tool status", async () => {
    const user = userEvent.setup();
    render(
      <ChatMessage
        assistantName="Discovery Scout"
        showReasoning
        message={{
          id: "a1",
          role: "assistant",
          parts: [{
            kind: "tool",
            callId: "tool-1",
            name: "search_jobs",
            argsPreview: "remote climate",
            resultPreview: "12 matches",
            ok: true,
            done: true,
          }],
        }}
      />,
    );
    expect(screen.getByText("Discovery Scout")).toBeInTheDocument();
    expect(screen.getByText("search jobs")).toBeInTheDocument();
    expect(screen.getByText("search jobs: Completed")).toHaveClass("sr-only");
    await user.click(screen.getByRole("button", { name: /search jobs/i }));
    expect(screen.getByText("12 matches")).toBeVisible();
  });

  it("keeps reasoning in an accessible disclosure", async () => {
    const user = userEvent.setup();
    render(
      <ChatMessage
        showReasoning
        message={{ id: "a2", role: "assistant", parts: [{ kind: "reasoning", text: "Checking evidence" }] }}
      />,
    );
    expect(screen.getByText("Checking evidence")).not.toBeVisible();
    await user.click(screen.getByRole("button", { name: "Working notes" }));
    expect(screen.getByText("Checking evidence")).toBeVisible();
  });

  it("groups consecutive reasoning and tool work into one activity region", () => {
    render(
      <ChatMessage
        showReasoning
        message={{
          id: "a-activity",
          role: "assistant",
          parts: [
            { kind: "reasoning", text: "Choosing sources" },
            {
              kind: "tool",
              callId: "tool-activity",
              name: "check_source",
              argsPreview: "example.com",
              resultPreview: "Verified",
              ok: true,
              done: true,
            },
          ],
        }}
      />,
    );

    expect(screen.getAllByRole("region", { name: "Agent activity" })).toHaveLength(1);
    expect(screen.getByText("1 completed")).toBeInTheDocument();
    expect(screen.getByText("Completed")).toBeVisible();
  });

  it("does not add an assistant label to user messages", () => {
    render(
      <ChatMessage
        assistantName="Interviewer"
        showReasoning
        message={{ id: "u1", role: "user", parts: [{ kind: "text", text: "My answer" }] }}
      />,
    );
    expect(screen.getByText("My answer")).toBeInTheDocument();
    expect(screen.queryByText("Interviewer")).not.toBeInTheDocument();
  });

  it("anchors assistant turns left and user turns right", () => {
    const { rerender } = render(
      <ChatMessage
        showReasoning
        message={{ id: "a3", role: "assistant", parts: [{ kind: "text", text: "A clear follow-up." }] }}
      />,
    );
    expect(screen.getByTestId("chat-message")).toHaveClass("justify-start");

    rerender(
      <ChatMessage
        showReasoning
        message={{ id: "u2", role: "user", parts: [{ kind: "text", text: "My answer." }] }}
      />,
    );
    const message = screen.getByTestId("chat-message");
    expect(message).toHaveClass("justify-end");
    expect(message.firstElementChild).toHaveTextContent("My answer.");
  });
});
