import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { changeLanguage } from "@/i18n";
import { getSettingsNavigation, SettingsLayout } from "./SettingsLayout";

describe("SettingsLayout", () => {
  it("updates navigation labels after switching language without remounting the page", async () => {
    render(<MemoryRouter><SettingsLayout /></MemoryRouter>);
    await act(() => changeLanguage("zh-CN"));
    expect(screen.getByRole("link", { name: "备份" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "助手提示词" })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "设置分区" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "邮件与通知" })).toBeInTheDocument();
    await act(() => changeLanguage("en"));
    expect(screen.getByRole("link", { name: "Backup" })).toBeInTheDocument();
  });
  it("renders one nav link per settings area, bucketed into labelled groups", () => {
    render(
      <MemoryRouter initialEntries={["/settings/search"]}>
        <Routes>
          <Route path="/settings" element={<SettingsLayout />}>
            <Route path="search" element={<div>search page</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );
    for (const item of getSettingsNavigation().nav) {
      expect(screen.getByRole("link", { name: item.label })).toBeInTheDocument();
    }
    for (const group of getSettingsNavigation().groups) {
      expect(screen.getByText(group.label)).toBeInTheDocument();
    }
    expect(screen.getByText("search page")).toBeInTheDocument();
  });

  it("groups job cleanup, resume output, application email, and AI controls with their related settings", () => {
    render(<MemoryRouter><SettingsLayout /></MemoryRouter>);
    expect(within(screen.getByRole("list", { name: "Discovery" })).getByRole("link", { name: "Pruning" }))
      .toHaveAttribute("href", "/settings/pruning");
    expect(within(screen.getByRole("list", { name: "Resumes" })).getByRole("link", { name: "Rendering" }))
      .toHaveAttribute("href", "/settings/rendering");
    expect(within(screen.getByRole("list", { name: "Applications" })).getByRole("link", { name: "Email & notifications" }))
      .toHaveAttribute("href", "/settings/notifications");
    expect(within(screen.getByRole("list", { name: "AI configuration" })).getByRole("link", { name: "API keys & models" }))
      .toHaveAttribute("href", "/settings/keys");
  });

  it.each(["/settings/search", "/settings/search/"])("keeps the grouped section picker in sync when navigating from %s", async (entry) => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={[entry]}>
        <Routes>
          <Route path="/settings" element={<SettingsLayout />}>
            <Route path="search" element={<div>search page</div>} />
            <Route path="notifications" element={<div>email page</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );
    const picker = screen.getByRole("combobox", { name: "Settings section" });
    expect(picker).toHaveValue("/settings/search");
    await user.selectOptions(picker, "/settings/notifications");
    expect(screen.getByText("email page")).toBeInTheDocument();
    expect(picker).toHaveValue("/settings/notifications");
    expect(screen.getByRole("link", { name: "Email & notifications" })).toHaveAttribute("aria-current", "page");
    expect(within(screen.getByRole("group", { name: "Applications" })).getByRole("option", { name: "Email & notifications" }))
      .toHaveValue("/settings/notifications");
  });

  it("no longer surfaces the relocated profile tab", () => {
    expect(getSettingsNavigation().nav.some((i) => i.to === "/settings/profile")).toBe(false);
  });
});
