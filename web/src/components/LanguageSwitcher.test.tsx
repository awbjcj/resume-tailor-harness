import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "@/test/server";
import { StrictMode } from "react";
import { toast } from "sonner";

import { DEFAULT_LANGUAGE, changeLanguage } from "@/i18n";
import { LanguageSwitcher } from "./LanguageSwitcher";

describe("LanguageSwitcher", () => {
  afterEach(async () => {
    await act(() => changeLanguage(DEFAULT_LANGUAGE));
    vi.restoreAllMocks();
  });

  it("switches the interface language", async () => {
    const user = userEvent.setup();
    render(<LanguageSwitcher />);

    await user.selectOptions(screen.getByRole("combobox", { name: "Language" }), "zh-CN");

    await waitFor(() => {
      expect(screen.getByRole("combobox", { name: "语言" })).toHaveValue("zh-CN");
    });
  });

  it("saves the dashboard language for emails when changed", async () => {
    const saved: string[] = [];
    server.use(http.put("/api/config/language", async ({ request }) => {
      const body = await request.json() as { language: string };
      saved.push(body.language);
      return HttpResponse.json(body);
    }));
    const user = userEvent.setup();
    render(<StrictMode><LanguageSwitcher persist /></StrictMode>);
    await waitFor(() => expect(saved).toEqual(["en"]));
    await user.selectOptions(screen.getByRole("combobox", { name: "Language" }), "zh-CN");
    await waitFor(() => expect(saved).toEqual(["en", "zh-CN"]));
    await user.selectOptions(screen.getByRole("combobox", { name: "语言" }), "en");
    await waitFor(() => expect(saved).toEqual(["en", "zh-CN", "en"]));
  });

  it("shows a Chinese message when the dashboard language cannot be saved", async () => {
    await changeLanguage("zh-CN");
    const failed = vi.spyOn(toast, "error").mockReturnValue("language-error");
    server.use(http.put("/api/config/language", () => HttpResponse.json({ error: { code: "UNAVAILABLE", message: "Unavailable" } }, { status: 503 })));
    render(<LanguageSwitcher persist />);
    await waitFor(() => expect(failed).toHaveBeenCalledWith("语言设置未保存成功，请重试。"));
  });
});
