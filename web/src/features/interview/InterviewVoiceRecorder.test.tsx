import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ChatComposer } from "@/components/chat/ChatComposer";

vi.mock("@/lib/api/client", () => ({ authHeaders: () => ({}) }));
vi.mock("@/components/TranscribeButton", () => ({ TranscribeButton: () => null }));

const getUserMedia = vi.fn();
class FakeRecorder {
  state = "inactive";
  mimeType = "audio/webm";
  ondataavailable: ((event: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  stream: { getTracks: () => { stop: () => void }[] };
  constructor(stream: { getTracks: () => { stop: () => void }[] }) { this.stream = stream; }
  start() { this.state = "recording"; }
  stop() {
    this.state = "inactive";
    this.ondataavailable?.({ data: new Blob(["recording"]) });
    this.onstop?.();
  }
}

function Wrapper({ children }: { children: ReactNode }) {
  const [client] = useState(() => new QueryClient({ defaultOptions: { queries: { retry: false } } }));
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function Composer({ send }: { send: (text: string) => void }) {
  const [value, setValue] = useState("");
  return <ChatComposer value={value} onChange={setValue} onSend={() => send(value)} onStop={() => {}} busy={false} interviewVoice ariaLabel="Your answer" />;
}

const available = {
  enabled: true, available: true, warning: false, optionalWorkPaused: false,
  spentMicros: 50, heldMicros: 10, remainingMicros: 10_000,
};

beforeEach(() => {
  getUserMedia.mockResolvedValue({ getTracks: () => [{ stop: vi.fn() }] });
  vi.stubGlobal("navigator", { mediaDevices: { getUserMedia } });
  vi.stubGlobal("MediaRecorder", FakeRecorder);
  vi.stubGlobal("fetch", vi.fn(async (url: string) => url.endsWith("/availability")
    ? { ok: true, json: async () => available }
    : { ok: true, json: async () => ({ text: "original answer", billingPending: false }) }));
});

afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); vi.clearAllMocks(); });

describe("interview voice recording", () => {
  it("puts a transcript in the editable field and sends only after explicit confirmation", async () => {
    const send = vi.fn();
    render(<Composer send={send} />, { wrapper: Wrapper });
    await userEvent.click(await screen.findByRole("button", { name: /record answer/i }));
    await userEvent.click(await screen.findByRole("button", { name: /stop and transcribe/i }));
    const input = await screen.findByRole("textbox", { name: /your answer/i });
    await waitFor(() => expect(input).toHaveValue("original answer"));
    expect(send).not.toHaveBeenCalled();
    await userEvent.clear(input);
    await userEvent.type(input, "edited answer");
    await userEvent.click(screen.getByRole("button", { name: /send message/i }));
    expect(send).toHaveBeenCalledWith("edited answer");
  });

  it("discards a recording without uploading it", async () => {
    render(<Composer send={vi.fn()} />, { wrapper: Wrapper });
    await userEvent.click(await screen.findByRole("button", { name: /record answer/i }));
    await userEvent.click(await screen.findByRole("button", { name: /discard/i }));
    expect(vi.mocked(fetch).mock.calls.filter(([url]) => String(url).endsWith("/official"))).toHaveLength(0);
    expect(screen.getByRole("textbox", { name: /your answer/i })).toHaveValue("");
  });

  it("uses the same request ID when retrying a failed upload", async () => {
    let attempts = 0;
    vi.mocked(fetch).mockImplementation(async (url) => {
      if (String(url).endsWith("/availability")) return { ok: true, json: async () => available } as Response;
      attempts += 1;
      return { ok: attempts > 1, json: async () => ({ text: "recovered", billingPending: false }) } as Response;
    });
    render(<Composer send={vi.fn()} />, { wrapper: Wrapper });
    await userEvent.click(await screen.findByRole("button", { name: /record answer/i }));
    await userEvent.click(await screen.findByRole("button", { name: /stop and transcribe/i }));
    await userEvent.click(await screen.findByRole("button", { name: /try again/i }));
    await screen.findByDisplayValue("recovered");
    const uploads = vi.mocked(fetch).mock.calls.filter(([url]) => String(url).endsWith("/official"));
    expect(uploads).toHaveLength(2);
    expect((uploads[0][1]?.body as FormData).get("request_id")).toBe((uploads[1][1]?.body as FormData).get("request_id"));
  });

  it("cancels an upload and ignores any late transcript", async () => {
    let finish!: (value: Response) => void;
    vi.mocked(fetch).mockImplementation(async (url) => {
      if (String(url).endsWith("/availability")) return { ok: true, json: async () => available } as Response;
      return new Promise((resolve) => { finish = resolve; });
    });
    render(<Composer send={vi.fn()} />, { wrapper: Wrapper });
    await userEvent.click(await screen.findByRole("button", { name: /record answer/i }));
    await userEvent.click(await screen.findByRole("button", { name: /stop and transcribe/i }));
    const upload = vi.mocked(fetch).mock.calls.find(([url]) => String(url).endsWith("/official"));
    await userEvent.click(await screen.findByRole("button", { name: /cancel/i }));
    await act(async () => finish({ ok: true, json: async () => ({ text: "late", billingPending: false }) } as Response));
    expect(upload?.[1]?.signal?.aborted).toBe(true);
    expect(screen.getByRole("textbox", { name: /your answer/i })).toHaveValue("");
  });

  it("keeps text usable when the optional budget is exhausted", async () => {
    vi.mocked(fetch).mockResolvedValue({ ok: true, json: async () => ({ ...available, available: false, optionalWorkPaused: true }) } as Response);
    const send = vi.fn();
    render(<Composer send={send} />, { wrapper: Wrapper });
    expect(await screen.findByText(/voice is paused/i)).toBeInTheDocument();
    await userEvent.type(screen.getByRole("textbox", { name: /your answer/i }), "typed answer");
    await userEvent.click(screen.getByRole("button", { name: /send message/i }));
    expect(send).toHaveBeenCalledWith("typed answer");
  });

  it("stops recording automatically at the two-minute limit", async () => {
    render(<Composer send={vi.fn()} />, { wrapper: Wrapper });
    const record = await screen.findByRole("button", { name: /record answer/i });
    vi.useFakeTimers();
    await act(async () => { fireEvent.click(record); await Promise.resolve(); });
    expect(screen.getByRole("button", { name: /stop and transcribe/i })).toBeInTheDocument();
    await act(async () => { vi.advanceTimersByTime(120_000); await Promise.resolve(); });
    expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).endsWith("/official"))).toBe(true);
  });
});
