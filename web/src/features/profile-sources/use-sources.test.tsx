import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  active: null as { status: string } | null,
  launch: vi.fn(),
}));

vi.mock("@/features/runs/use-active-run", () => ({
  useActiveRun: () => mocks.active,
}));

vi.mock("@/features/runs/use-launch-run", () => ({
  launchers: { githubSync: vi.fn() },
  useLaunchRun: () => ({ launch: mocks.launch }),
}));

import { useSyncGithub } from "./use-sources";
import { useDeleteSource, useReplaceSource, useUploadSources } from "./use-sources";
import { server } from "@/test/server";

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>
);

describe("useSyncGithub", () => {
  beforeEach(() => {
    mocks.active = null;
    mocks.launch.mockReset();
  });

  it("stays pending while the tracked run launch request is in flight", async () => {
    let finish!: (value: boolean) => void;
    mocks.launch.mockReturnValue(new Promise<boolean>((resolve) => { finish = resolve; }));
    const { result } = renderHook(() => useSyncGithub());

    act(() => result.current.mutate());
    expect(result.current.isPending).toBe(true);

    act(() => finish(true));
    await waitFor(() => expect(result.current.isPending).toBe(false));
  });

  it.each(["queued", "running", "cancelling"])(
    "is pending for a %s run",
    (status) => {
      mocks.active = { status };
      const { result } = renderHook(() => useSyncGithub());
      expect(result.current.isPending).toBe(true);
    },
  );
});

describe("useUploadSources", () => {
  it("uploads a batch sequentially and isolates failures", async () => {
    let calls = 0;
    server.use(
      http.post("/api/profile/sources", () => {
        calls += 1;
        if (calls === 2) {
          return HttpResponse.json(
            { error: { code: "BAD_FILE", message: "unsupported" } },
            { status: 400 },
          );
        }
        return HttpResponse.json({ id: `doc-${calls}` });
      }),
    );
    const { result } = renderHook(() => useUploadSources(), { wrapper });
    const files = [
      new File(["a"], "a.md", { type: "text/markdown" }),
      new File(["b"], "b.md", { type: "text/markdown" }),
      new File(["c"], "c.md", { type: "text/markdown" }),
    ];

    const summary = await result.current.uploadAll(files, "literal", null);

    expect(summary.ok).toBe(2);
    expect(summary.failed).toEqual([["b.md", "unsupported"]]);
    expect(calls).toBe(3);
  });
});

describe("source mutations", () => {
  it("replaces a dossier in one request without uploading a new primary or deleting it", async () => {
    const calls: string[] = [];
    server.use(
      http.put("/api/profile/sources/project/file", async ({ request }) => {
        calls.push("replace");
        const form = await request.formData();
        expect(form.get("file")).toMatchObject({ size: 7 });
        expect(form.has("mode")).toBe(false);
        expect(form.has("primary")).toBe(false);
        return HttpResponse.json({ id: "project", mode: "project", primary: false });
      }),
      http.post("/api/profile/sources", () => { calls.push("upload"); return HttpResponse.error(); }),
      http.delete("/api/profile/sources/project", () => { calls.push("delete"); return HttpResponse.error(); }),
    );
    const { result } = renderHook(() => useReplaceSource(), { wrapper });
    await act(async () => {
      await result.current.mutateAsync({ oldId: "project", file: new File(["updated"], "dossier.md") });
    });
    expect(calls).toEqual(["replace"]);
  });

  it("purges the stored file when the user removes a source", async () => {
    let purge: string | null = null;
    server.use(http.delete("/api/profile/sources/project", ({ request }) => {
      purge = new URL(request.url).searchParams.get("purge");
      return new HttpResponse(null, { status: 204 });
    }));
    const { result } = renderHook(() => useDeleteSource(), { wrapper });
    await act(async () => { await result.current.mutateAsync("project"); });
    expect(purge).toBe("true");
  });
});
