import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useViewMode } from "./use-view-mode";

function wrapper({ children }: { children: ReactNode }) {
  return <MemoryRouter initialEntries={["/?job=7"]}>{children}</MemoryRouter>;
}

describe("useViewMode", () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => vi.restoreAllMocks());

  it("still renders and changes view when browser storage is blocked", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("Blocked", "SecurityError");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("Blocked", "SecurityError");
    });
    const { result } = renderHook(() => useViewMode(), { wrapper });
    expect(result.current[0]).toBe("cards");
    act(() => result.current[1]("list"));
    expect(result.current[0]).toBe("list");
  });

  it("persists list view and preserves unrelated URL parameters", () => {
    const { result } = renderHook(
      () => ({ view: useViewMode("test-view"), location: useLocation() }),
      { wrapper },
    );
    act(() => result.current.view[1]("list"));
    expect(result.current.view[0]).toBe("list");
    expect(localStorage.getItem("test-view")).toBe("list");
    expect(result.current.location.search).toContain("job=7");
    expect(result.current.location.search).toContain("view=list");
  });
});
