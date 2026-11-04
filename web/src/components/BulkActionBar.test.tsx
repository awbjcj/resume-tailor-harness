import { act, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { BulkActionBar } from "./BulkActionBar";
import { changeLanguage } from "@/i18n";

describe("BulkActionBar", () => {
  it("offers select-all-matching only when all loaded rows are selected", () => {
    const props = {
      isAllMatching: false,
      pageCount: 50,
      total: 120,
      onSelectAllMatching: vi.fn(),
      onClear: vi.fn(),
      children: null,
    };
    const { rerender } = render(<BulkActionBar {...props} count={1} />);
    expect(screen.queryByText(/Select all 120/)).not.toBeInTheDocument();
    rerender(<BulkActionBar {...props} count={50} />);
    expect(screen.getByText(/Select all 120/)).toBeInTheDocument();
  });

  it("localizes the selection banner and its matching-results action", async () => {
    await changeLanguage("zh-CN");
    const onSelectAllMatching = vi.fn();
    render(<BulkActionBar count={2} pageCount={2} total={5} isAllMatching={false}
      onSelectAllMatching={onSelectAllMatching} onClear={vi.fn()}>{null}</BulkActionBar>);
    expect(screen.getByRole("status", { name: "已选择 2 项" })).toBeInTheDocument();
    expect(screen.getByText("已选中全部 2 条已加载的结果。")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "选中符合此筛选条件的全部 5 条结果" })).toBeInTheDocument();
    await act(() => changeLanguage("en"));
    expect(screen.getByRole("status", { name: "2 selected" })).toBeInTheDocument();
  });
});
