import { act, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { changeLanguage } from "@/i18n";
import { getSettingsNavigation, SettingsLayout } from "./SettingsLayout";

describe("SettingsLayout", () => {
  it("updates navigation labels after switching language without remounting the page", async () => {
    render(<MemoryRouter><SettingsLayout /></MemoryRouter>);
    await act(() => changeLanguage("zh-CN"));
    expect(screen.getAllByRole("link", { name: "备份" })).toHaveLength(2);
    expect(screen.getAllByRole("link", { name: "助手提示词" })).toHaveLength(2);
    await act(() => changeLanguage("en"));
    expect(screen.getAllByRole("link", { name: "Backup" })).toHaveLength(2);
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
      expect(screen.getAllByRole("link", { name: item.label })).toHaveLength(2);
    }
    for (const group of getSettingsNavigation().groups) {
      expect(screen.getByText(group.label)).toBeInTheDocument();
    }
    expect(screen.getByText("search page")).toBeInTheDocument();
  });

  it("no longer surfaces the relocated profile tab", () => {
    expect(getSettingsNavigation().nav.some((i) => i.to === "/settings/profile")).toBe(false);
  });
});
