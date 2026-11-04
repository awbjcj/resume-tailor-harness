import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { emptyFilterState } from "@/lib/filters/types";

import { ActiveFilterSummary } from "./ActiveFilterSummary";
import { changeLanguage } from "@/i18n";

describe("ActiveFilterSummary", () => {
  it("renders a removable chip per active value and clears filters", () => {
    const filter = emptyFilterState();
    filter.seniority = new Set(["senior"]);
    const onRemove = vi.fn();
    const onClear = vi.fn();
    render(
      <ActiveFilterSummary
        filter={filter}
        onRemove={onRemove}
        onClear={onClear}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /senior/i }));
    expect(onRemove).toHaveBeenCalledWith("seniority", "senior");
    fireEvent.click(screen.getByRole("button", { name: "Clear all" }));
    expect(onClear).toHaveBeenCalledOnce();
  });

  it("localizes known facets while retaining the raw values used for removal", async () => {
    await changeLanguage("zh-CN");
    const filter = emptyFilterState();
    filter.seniority = new Set(["senior"]);
    filter.status = new Set(["approved"]);
    filter.skills = new Set(["Python"]);
    const onRemove = vi.fn();
    render(<ActiveFilterSummary filter={filter} onRemove={onRemove} onClear={vi.fn()} />);
    expect(screen.getByRole("button", { name: "已批准" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Python" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "高级" }));
    expect(onRemove).toHaveBeenCalledWith("seniority", "senior");
  });
});
