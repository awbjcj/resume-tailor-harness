import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TranscribeButton } from "./TranscribeButton";

const mocks = vi.hoisted(() => ({ unwrap: vi.fn(), get: vi.fn() }));

vi.mock("@/lib/api/client", () => ({
  api: { GET: mocks.get },
  unwrap: mocks.unwrap,
  authHeaders: () => ({ Authorization: "Bearer test-token" }),
}));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

const getUserMedia = vi.fn();

class FakeRecorder {
  state = "inactive";
  mimeType = "audio/mp4";
  ondataavailable: ((event: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  stream: { getTracks: () => { stop: () => void }[] };
  constructor(stream: { getTracks: () => { stop: () => void }[] }) {
    this.stream = stream;
  }
  start() { this.state = "recording"; }
  stop() {
    this.state = "inactive";
    this.ondataavailable?.({ data: new Blob(["audio"]) });
    this.onstop?.();
  }
}

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient();
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.unwrap.mockResolvedValue({ available: true });
  getUserMedia.mockResolvedValue({ getTracks: () => [{ stop: vi.fn() }] });
  vi.stubGlobal("navigator", { mediaDevices: { getUserMedia } });
  vi.stubGlobal("MediaRecorder", FakeRecorder);
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({ ok: true, json: async () => ({ text: "hello world" }) }),
  );
});

afterEach(() => vi.unstubAllGlobals());

describe("TranscribeButton", () => {
  it("releases the microphone without uploading when unmounted while recording", async () => {
    const stopTrack = vi.fn();
    getUserMedia.mockResolvedValue({ getTracks: () => [{ stop: stopTrack }] });
    const { unmount } = render(<TranscribeButton onText={vi.fn()} />, { wrapper });
    await userEvent.click(await screen.findByRole("button", { name: /record a voice answer/i }));
    await screen.findByRole("button", { name: /stop recording/i });
    unmount();
    expect(stopTrack).toHaveBeenCalled();
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it("releases permission results that arrive after unmount and prevents duplicate requests", async () => {
    const stopTrack = vi.fn();
    let resolvePermission!: (stream: { getTracks: () => { stop: () => void }[] }) => void;
    getUserMedia.mockReturnValue(new Promise((resolve) => { resolvePermission = resolve; }));
    const { unmount } = render(<TranscribeButton onText={vi.fn()} />, { wrapper });
    const record = await screen.findByRole("button", { name: /record a voice answer/i });
    await userEvent.dblClick(record);
    expect(getUserMedia).toHaveBeenCalledTimes(1);
    unmount();
    await act(async () => resolvePermission({ getTracks: () => [{ stop: stopTrack }] }));
    expect(stopTrack).toHaveBeenCalled();
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it("aborts an upload and does not deliver text after unmount", async () => {
    const onText = vi.fn();
    let resolveUpload!: (response: Response) => void;
    vi.mocked(fetch).mockReturnValue(new Promise((resolve) => { resolveUpload = resolve; }));
    const { unmount } = render(<TranscribeButton onText={onText} />, { wrapper });
    await userEvent.click(await screen.findByRole("button", { name: /record a voice answer/i }));
    await userEvent.click(await screen.findByRole("button", { name: /stop recording/i }));
    await waitFor(() => expect(fetch).toHaveBeenCalled());
    const options = vi.mocked(fetch).mock.calls[0][1]!;
    unmount();
    await act(async () => resolveUpload(new Response(JSON.stringify({ text: "late" }))));
    expect(options.signal?.aborted).toBe(true);
    expect(onText).not.toHaveBeenCalled();
  });

  it("releases the microphone if the recorder cannot start", async () => {
    const stopTrack = vi.fn();
    getUserMedia.mockResolvedValue({ getTracks: () => [{ stop: stopTrack }] });
    vi.stubGlobal("MediaRecorder", class extends FakeRecorder {
      start() { throw new Error("Unsupported recording"); }
    });
    render(<TranscribeButton onText={vi.fn()} />, { wrapper });
    await userEvent.click(await screen.findByRole("button", { name: /record a voice answer/i }));
    expect(stopTrack).toHaveBeenCalled();
  });

  it("renders nothing when transcription is unavailable", async () => {
    mocks.unwrap.mockResolvedValue({ available: false });
    const { container } = render(<TranscribeButton onText={vi.fn()} />, { wrapper });
    await waitFor(() => expect(mocks.unwrap).toHaveBeenCalled());
    expect(container.querySelector("button")).toBeNull();
  });

  it("records, uploads, and forwards the transcript", async () => {
    const onText = vi.fn();
    render(<TranscribeButton onText={onText} />, { wrapper });
    const record = await screen.findByRole("button", { name: /record a voice answer/i });

    await userEvent.click(record);
    const stop = await screen.findByRole("button", { name: /stop recording/i });
    await userEvent.click(stop);

    await waitFor(() => expect(onText).toHaveBeenCalledWith("hello world"));
    expect(globalThis.fetch).toHaveBeenCalledWith(
      "/api/transcribe",
      expect.objectContaining({ method: "POST" }),
    );
    const options = vi.mocked(fetch).mock.calls[0][1]!;
    expect(options.headers).toEqual({ Authorization: "Bearer test-token" });
    const file = (options.body as FormData).get("file") as File;
    expect(file.type).toBe("audio/mp4");
    expect(file.name).toBe("clip.mp4");
  });

  it("keeps the blob for retry after a failed upload", async () => {
    const onText = vi.fn();
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ ok: false });
    render(<TranscribeButton onText={onText} />, { wrapper });

    await userEvent.click(await screen.findByRole("button", { name: /record a voice answer/i }));
    await userEvent.click(await screen.findByRole("button", { name: /stop recording/i }));

    const retry = await screen.findByRole("button", { name: /retry transcription/i });
    expect(getUserMedia).toHaveBeenCalledTimes(1);

    await userEvent.click(retry);
    await waitFor(() => expect(onText).toHaveBeenCalledWith("hello world"));
    expect(getUserMedia).toHaveBeenCalledTimes(1); // no second capture
  });
});
