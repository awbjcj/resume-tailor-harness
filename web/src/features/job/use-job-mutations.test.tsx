import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "@/test/server";

const mocks = vi.hoisted(() => ({ launch: vi.fn() }));

vi.mock("@/features/runs/use-launch-run", () => ({
  useLaunchRun: () => ({ launch: mocks.launch }),
}));

import {
  useGenerateCoverLetter,
  useReviseCoverLetter,
  useReviseVersion,
  useSelectResume,
  useDeselectResume,
} from "./use-job-mutations";

function wrapper({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>
  );
}

describe("revision run mutations", () => {
  beforeEach(() => {
    mocks.launch.mockReset();
    mocks.launch.mockResolvedValue(true);
  });

  it("launches resume revision with retry metadata", async () => {
    const { result } = renderHook(() => useReviseVersion(3), { wrapper });

    await act(() =>
      result.current.mutateAsync({
        versionId: 5,
        instruction: "shorter",
        reReview: true,
      }),
    );

    expect(mocks.launch).toHaveBeenCalledWith(
      "revise",
      expect.any(Function),
      ["job"],
      { versionId: 5, jobId: 3, instruction: "shorter", reReview: true },
    );
  });

  it("launches cover-letter revision with retry metadata", async () => {
    const { result } = renderHook(() => useReviseCoverLetter(8), { wrapper });

    await act(() =>
      result.current.mutateAsync({ coverLetterId: 7, instruction: "warmer" }),
    );

    expect(mocks.launch).toHaveBeenCalledWith(
      "coverLetterRevise",
      expect.any(Function),
      ["job"],
      { coverLetterId: 7, jobId: 8, instruction: "warmer" },
    );
  });

  it("launches cover-letter generation scoped to one job", async () => {
    const { result } = renderHook(() => useGenerateCoverLetter(4), { wrapper });

    await act(() => result.current.mutateAsync());

    expect(mocks.launch).toHaveBeenCalledWith(
      "coverLetter",
      expect.any(Function),
      // Board invalidation stays at the launch default, unlike the revise
      // mutations above: a first cover letter can change a job's board row.
      undefined,
      { jobId: 4 },
    );
  });
});

it("refreshes dashboard readiness when the exact resume selection changes", async () => {
  server.use(
    http.post("/api/jobs/17/select-resume/3", () => HttpResponse.json({ jobId: 17, resumeVersionId: 3 })),
    http.delete("/api/jobs/17/select-resume", () => HttpResponse.json({ jobId: 17, resumeVersionId: null })),
  );
  const qc = new QueryClient();
  const invalidate = vi.spyOn(qc, "invalidateQueries");
  const { result } = renderHook(() => ({ select: useSelectResume(17), deselect: useDeselectResume(17) }), { wrapper: ({ children }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider> });
  await act(() => result.current.select.mutateAsync(3));
  expect(invalidate).toHaveBeenCalledWith({ queryKey: ["dashboard-summary"] });
  invalidate.mockClear();
  await act(() => result.current.deselect.mutateAsync());
  expect(invalidate).toHaveBeenCalledWith({ queryKey: ["dashboard-summary"] });
});
