import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ChatThread } from "./ChatThread";

const renders = vi.hoisted(() => ({ textParts: 0 }));
vi.mock("./parts/TextPart", () => ({
  TextPart: ({ text, caret }: { text: string; caret?: boolean }) => {
    renders.textParts += 1;
    return <div data-testid="chat-part-text" data-caret={caret}>{text}</div>;
  },
}));

describe("ChatThread", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("renders message and streamed parts in arrival order", () => {
    render(
      <ChatThread
        messages={[{ id: "u", role: "user", parts: [{ kind: "text", text: "hi" }] }]}
        streaming={[
          { kind: "text", text: "checking" },
          {
            kind: "tool",
            callId: "c1",
            name: "search",
            argsPreview: "Kafka",
            resultPreview: "",
            ok: true,
            done: false,
          },
          { kind: "text", text: "done" },
        ]}
      />,
    );
    expect(screen.getAllByTestId(/chat-part-/).map((node) => node.dataset.testid)).toEqual([
      "chat-part-text",
      "chat-part-text",
      "chat-part-tool",
      "chat-part-text",
    ]);
  });

  it("hides reasoning when disabled", () => {
    render(
      <ChatThread
        messages={[]}
        streaming={[{ kind: "reasoning", text: "private" }]}
        showReasoning={false}
      />,
    );
    expect(screen.queryByText("private")).not.toBeInTheDocument();
  });

  it("offers jump to latest after scrolling away", () => {
    render(<ChatThread messages={[]} streaming={null} />);
    const viewport = screen.getByTestId("chat-viewport");
    Object.defineProperties(viewport, {
      scrollHeight: { value: 1000, configurable: true },
      clientHeight: { value: 200, configurable: true },
      scrollTop: { value: 100, configurable: true, writable: true },
    });
    fireEvent.scroll(viewport);
    expect(screen.getByRole("button", { name: /jump to latest/i })).toBeInTheDocument();
  });

  it("does not re-render durable text parts for each streaming delta", () => {
    renders.textParts = 0;
    const messages = Array.from({ length: 20 }, (_, index) => ({
      id: `m-${index}`,
      role: "assistant" as const,
      parts: [{ kind: "text" as const, text: `durable ${index}` }],
    }));
    const { rerender } = render(
      <ChatThread messages={messages} streaming={[{ kind: "text", text: "a" }]} />,
    );
    expect(renders.textParts).toBe(21);
    rerender(
      <ChatThread messages={messages} streaming={[{ kind: "text", text: "ab" }]} />,
    );
    expect(renders.textParts).toBe(22);
  });

  it("clears the caret when prose settles", () => {
    const { rerender } = render(
      <ChatThread messages={[]} streaming={[{ kind: "text", text: "answer" }]} />,
    );
    expect(screen.getByTestId("chat-part-text")).toHaveAttribute("data-caret", "true");
    rerender(
      <ChatThread messages={[]} streaming={[{ kind: "text", text: "answer" }]} streamingActive={false} />,
    );
    expect(screen.getByTestId("chat-part-text")).toHaveAttribute("data-caret", "false");
  });

  it("keeps streaming prose outside live status regions", () => {
    render(<ChatThread messages={[]} streaming={[{ kind: "text", text: "Reading the answer" }]} />);
    const response = screen.getByTestId("chat-streaming-response");
    expect(response).toHaveAttribute("aria-busy", "true");
    expect(screen.getByText("Reading the answer").closest('[role="status"], [aria-live]')).toBeNull();
    expect(screen.getByRole("status")).toHaveTextContent("Responding");
  });

  it("follows late content resizing only while the reader is bottom-pinned", () => {
    let resized = () => {};
    const disconnected = vi.fn();
    const frames: FrameRequestCallback[] = [];
    vi.stubGlobal("ResizeObserver", class {
      constructor(callback: () => void) { resized = callback; }
      observe() {}
      disconnect = disconnected;
    });
    vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => frames.push(callback));
    vi.stubGlobal("cancelAnimationFrame", vi.fn());

    const { unmount } = render(<ChatThread messages={[]} streaming={null} />);
    const viewport = screen.getByTestId("chat-viewport");
    Object.defineProperties(viewport, {
      scrollHeight: { value: 1000, configurable: true },
      clientHeight: { value: 200, configurable: true },
      scrollTop: { value: 800, configurable: true, writable: true },
    });
    act(() => { while (frames.length) frames.shift()!(0); });
    Object.defineProperty(viewport, "scrollHeight", { value: 1400, configurable: true });
    act(() => { resized(); resized(); });
    expect(frames).toHaveLength(1);
    act(() => { while (frames.length) frames.shift()!(0); });
    expect(viewport.scrollTop).toBe(1400);

    viewport.scrollTop = 100;
    fireEvent.scroll(viewport);
    expect(disconnected).toHaveBeenCalledOnce();
    expect(screen.getByRole("button", { name: /jump to latest/i })).toBeInTheDocument();
    Object.defineProperty(viewport, "scrollHeight", { value: 1800, configurable: true });
    expect(viewport.scrollTop).toBe(100);
    fireEvent.click(screen.getByRole("button", { name: /jump to latest/i }));
    expect(viewport.scrollTop).toBe(1800);
    unmount();
    expect(disconnected).toHaveBeenCalledTimes(2);
  });

  it("does not mount reasoning text while its disclosure is collapsed", () => {
    render(<ChatThread messages={[]} streaming={[{ kind: "reasoning", text: "private chain" }]} />);
    expect(screen.getByText("private chain")).not.toBeVisible();
  });

  it("forwards the page-specific assistant identity", () => {
    render(
      <ChatThread
        messages={[{ id: "a", role: "assistant", parts: [{ kind: "text", text: "hello" }] }]}
        streaming={null}
        assistantName="Profile Coach"
        assistantIcon={<span data-testid="coach-icon" />}
      />,
    );
    expect(screen.getByText("Profile Coach")).toBeInTheDocument();
    expect(screen.getByTestId("coach-icon")).toBeInTheDocument();
  });
});
