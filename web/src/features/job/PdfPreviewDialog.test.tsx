import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { clearToken, createDownloadUrl, setToken } from "@/lib/api/client";
import { PdfPreviewDialog } from "./PdfPreviewDialog";

vi.mock("@/lib/api/client", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  createDownloadUrl: vi.fn(),
}));

const TITLE = "Round 0 preview";
const PREVIEW_URL = "http://localhost/api/resume-versions/7/preview?token=short-download-capability";

function dialog(open: boolean) {
  return (
    <PdfPreviewDialog
      open={open}
      onOpenChange={() => undefined}
      title={TITLE}
      previewPath="/api/resume-versions/7/preview"
      downloadPath="/api/resume-versions/7/pdf"
    />
  );
}

function renderDialog(open = true) {
  return render(dialog(open));
}

/** A fetch whose resolution the test schedules, so races are deterministic. */
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((settle) => {
    resolve = settle;
  });
  return { promise, resolve };
}

function pdfResponse() {
  return { ok: true, body: { cancel: vi.fn().mockResolvedValue(undefined) } } as unknown as Response;
}

describe("PdfPreviewDialog", () => {
  beforeEach(() => {
    vi.mocked(createDownloadUrl).mockReset().mockResolvedValue(PREVIEW_URL);
  });

  afterEach(() => {
    clearToken();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("authenticates the preview and retains the named HTTP response in the native viewer", async () => {
    setToken("preview-token");
    const response = pdfResponse();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));
    const createBlob = vi.spyOn(URL, "createObjectURL");

    renderDialog();

    const frame = await screen.findByTitle(TITLE);
    expect(frame).toHaveAttribute("src", PREVIEW_URL);
    expect(frame).toHaveAttribute("referrerpolicy", "no-referrer");
    expect(createBlob).not.toHaveBeenCalled();
    expect(response.body?.cancel).toHaveBeenCalled();
    expect(createDownloadUrl).toHaveBeenCalledWith(
      "/api/resume-versions/7/preview", expect.any(AbortSignal),
    );
    const [url, options] = vi.mocked(fetch).mock.calls[0];
    expect(String(url)).toContain("/api/resume-versions/7/preview");
    expect(new Headers(options?.headers).get("Authorization")).toBe(
      "Bearer preview-token",
    );
  });

  it("shows the API error envelope message instead of an iframe", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        json: vi
          .fn()
          .mockResolvedValue({ error: { message: "No rendered PDF for this version" } }),
      } as unknown as Response),
    );

    renderDialog();

    expect(
      await screen.findByText("No rendered PDF for this version"),
    ).toBeInTheDocument();
    expect(screen.queryByTitle(TITLE)).not.toBeInTheDocument();
  });

  it("aborts the preview request when the dialog closes", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(pdfResponse()));

    const { rerender } = renderDialog();
    await screen.findByTitle(TITLE);

    rerender(dialog(false));

    const [, options] = vi.mocked(fetch).mock.calls[0];
    expect(options?.signal?.aborted).toBe(true);
  });

  it("refetches and mints a fresh capability when the dialog is reopened", async () => {
    const secondFetch = deferred<Response>();
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(pdfResponse())
        .mockReturnValueOnce(secondFetch.promise),
    );
    vi.mocked(createDownloadUrl)
      .mockResolvedValueOnce(`${PREVIEW_URL}-first`)
      .mockResolvedValueOnce(`${PREVIEW_URL}-second`);

    const { rerender } = renderDialog();
    expect(await screen.findByTitle(TITLE)).toHaveAttribute("src", `${PREVIEW_URL}-first`);

    rerender(dialog(false));
    rerender(dialog(true));

    // Synchronous: reopening settles the deferred reset immediately rather
    // than flashing the previous PDF until the exit timer happens to fire.
    expect(screen.getByLabelText("Loading preview")).toBeInTheDocument();
    expect(screen.queryByTitle(TITLE)).not.toBeInTheDocument();

    secondFetch.resolve(pdfResponse());
    await waitFor(() =>
      expect(screen.getByTitle(TITLE)).toHaveAttribute("src", `${PREVIEW_URL}-second`),
    );
    expect(vi.mocked(fetch)).toHaveBeenCalledTimes(2);
  });

  it("clears a previous failure when the dialog is reopened", async () => {
    const retry = deferred<Response>();
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce({
          ok: false,
          json: vi.fn().mockResolvedValue({ error: { message: "Preview exploded" } }),
        } as unknown as Response)
        .mockReturnValueOnce(retry.promise),
    );

    const { rerender } = renderDialog();
    expect(await screen.findByRole("alert")).toHaveTextContent("Preview exploded");

    rerender(dialog(false));
    rerender(dialog(true));

    // Synchronous for the same reason: the stale failure must not survive the
    // reopen even for the length of the exit animation.
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    retry.resolve(pdfResponse());
    expect(await screen.findByTitle(TITLE)).toHaveAttribute("src", PREVIEW_URL);
  });

  it("ignores a stale response that resolves after the reopened one", async () => {
    const firstFetch = deferred<Response>();
    const secondFetch = deferred<Response>();
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockReturnValueOnce(firstFetch.promise)
        .mockReturnValueOnce(secondFetch.promise),
    );

    const { rerender } = renderDialog();
    rerender(dialog(false));
    rerender(dialog(true));

    const [, firstOptions] = vi.mocked(fetch).mock.calls[0];
    expect(firstOptions?.signal?.aborted).toBe(true);

    secondFetch.resolve(pdfResponse());
    expect(await screen.findByTitle(TITLE)).toHaveAttribute("src", PREVIEW_URL);

    // An abandoned request must not mint a second capability or change the frame.
    const stale = pdfResponse();
    firstFetch.resolve(stale);
    await waitFor(() => expect(stale.body?.cancel).toHaveBeenCalled());
    expect(createDownloadUrl).toHaveBeenCalledTimes(1);
    expect(screen.getByTitle(TITLE)).toHaveAttribute("src", PREVIEW_URL);
  });

  it("ignores an old capability that resolves after a reopened preview", async () => {
    const oldLink = deferred<string>();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(pdfResponse()));
    vi.mocked(createDownloadUrl).mockReturnValueOnce(oldLink.promise);
    const { rerender } = renderDialog();
    await waitFor(() => expect(createDownloadUrl).toHaveBeenCalledTimes(1));
    rerender(dialog(false));
    rerender(dialog(true));
    expect(await screen.findByTitle(TITLE)).toHaveAttribute("src", PREVIEW_URL);
    oldLink.resolve(`${PREVIEW_URL}-stale`);
    await waitFor(() => expect(createDownloadUrl).toHaveBeenCalledTimes(2));
    expect(screen.getByTitle(TITLE)).toHaveAttribute("src", PREVIEW_URL);
  });
});
