import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { toast } from "sonner";
import { server } from "@/test/server";
import { CopyApplicationPromptButton } from "./CopyApplicationPromptButton";

const prompt = "# Fill in my job application using the live browser\nAda at Acme";

afterEach(() => vi.restoreAllMocks());

describe("CopyApplicationPromptButton", () => {
  it("fetches the selected job on click and copies the exact English prompt", async () => {
    userEvent.setup();
    let requests = 0;
    const clipboard = vi.fn().mockResolvedValue(undefined);
    vi.spyOn(navigator, "clipboard", "get").mockReturnValue({ writeText: clipboard } as unknown as Clipboard);
    const parentClick = vi.fn();
    server.use(http.get("/api/jobs/42/application-prompt", () => {
      requests++;
      return HttpResponse.json({ prompt });
    }));
    render(<div onClick={parentClick}><CopyApplicationPromptButton jobId={42} compact /></div>);
    expect(requests).toBe(0);
    fireEvent.click(screen.getByRole("button", { name: "Copy application prompt" }));
    await waitFor(() => expect(clipboard).toHaveBeenCalledWith(prompt));
    expect(parentClick).not.toHaveBeenCalled();
    expect(requests).toBe(1);
  });

  it("provides selectable text when the clipboard is blocked", async () => {
    userEvent.setup();
    vi.spyOn(navigator, "clipboard", "get").mockReturnValue({ writeText: vi.fn().mockRejectedValue(new Error("blocked")) } as unknown as Clipboard);
    server.use(http.get("/api/jobs/7/application-prompt", () => HttpResponse.json({ prompt })));
    render(<CopyApplicationPromptButton jobId={7} />);
    fireEvent.click(screen.getByRole("button", { name: "Copy application prompt" }));
    expect(await screen.findByRole("textbox", { name: "English application prompt" })).toHaveValue(prompt);
    expect(screen.getByRole("link", { name: "Edit application profile" })).toHaveAttribute("href", "/settings/application-profile");
  });

  it("reports a failed request without claiming clipboard success", async () => {
    const error = vi.spyOn(toast, "error");
    server.use(http.get("/api/jobs/7/application-prompt", () => HttpResponse.json({ error: { code: "NOT_FOUND", message: "Missing" } }, { status: 404 })));
    render(<CopyApplicationPromptButton jobId={7} />);
    fireEvent.click(screen.getByRole("button", { name: "Copy application prompt" }));
    await waitFor(() => expect(error).toHaveBeenCalled());
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });
});
