import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { api, getToken, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { useActiveRun } from "@/features/runs/use-active-run";
import { launchers, useLaunchRun } from "@/features/runs/use-launch-run";

export type ProfileSource =
  components["schemas"]["resume_tailor_harness__api__schemas__profile__SourceOut"];
export type NoteInput = components["schemas"]["NoteIn"];
export type UrlInput = components["schemas"]["UrlIn"];

export type SkeletonEntry = { id: string; kind: string; label: string };
export const SOURCE_MUTATION_KEY = ["profile-source-mutation"] as const;

export function useSources() {
  return useQuery({
    queryKey: ["profile-sources"],
    queryFn: () =>
      unwrap(api.GET("/api/profile/sources", {} as never)) as Promise<
        ProfileSource[]
      >,
  });
}

export function useGithubExclusions() {
  return useQuery({
    queryKey: ["profile-source-exclusions"],
    queryFn: () => unwrap(api.GET("/api/profile/sources/github-exclusions")),
  });
}

export function useRestoreGithubSources() {
  const qc = useQueryClient();
  return useMutation({
    mutationKey: SOURCE_MUTATION_KEY,
    mutationFn: () =>
      unwrap(api.DELETE("/api/profile/sources/github-exclusions")),
    onSuccess: () =>
      toast.success(
        "GitHub sources restored. Sync GitHub to import them again.",
      ),
    onSettled: () =>
      Promise.all([
        qc.invalidateQueries({ queryKey: ["profile-source-exclusions"] }),
        qc.invalidateQueries({ queryKey: ["github-repositories"] }),
      ]),
    onError: (err: Error) => toast.error(err.message),
  });
}

export function useSkeleton() {
  return useQuery({
    queryKey: ["profile-skeleton"],
    queryFn: () =>
      unwrap(api.GET("/api/profile/skeleton", {} as never)) as Promise<
        SkeletonEntry[]
      >,
  });
}

async function postSource(
  file: File,
  mode?: string,
  anchor?: string | null,
  primary?: boolean,
): Promise<ProfileSource> {
  const form = new FormData();
  form.append("file", file);
  if (mode) form.append("mode", mode);
  if (anchor) form.append("anchor", anchor);
  if (primary) form.append("primary", "true");
  const headers: HeadersInit = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const resp = await fetch(`${window.location.origin}/api/profile/sources`, {
    method: "POST",
    body: form,
    headers,
  });
  const body = await resp.json();
  if (!resp.ok) throw new Error(body?.error?.message ?? "Upload failed");
  return body as ProfileSource;
}

export function useUploadSource() {
  const qc = useQueryClient();
  return useMutation({
    mutationKey: SOURCE_MUTATION_KEY,
    mutationFn: ({
      file,
      mode,
      anchor,
    }: {
      file: File;
      mode?: string;
      anchor?: string | null;
    }) => postSource(file, mode, anchor),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["profile-sources"] });
      qc.invalidateQueries({ queryKey: ["setup-status"] });
      qc.invalidateQueries({ queryKey: ["github-repositories"] });
      toast.success("Source added");
    },
    onError: (err: Error) => toast.error(err.message),
  });
}

export function useUploadSources() {
  const qc = useQueryClient();
  const uploadAll = async (
    files: File[],
    mode?: string,
    anchor?: string | null,
  ): Promise<{ ok: number; failed: [string, string][] }> => {
    let ok = 0;
    const failed: [string, string][] = [];
    for (const file of files) {
      try {
        await postSource(file, mode, anchor);
        ok += 1;
      } catch (error) {
        failed.push([file.name, (error as Error).message]);
      }
    }
    await qc.invalidateQueries({ queryKey: ["profile-sources"] });
    await qc.invalidateQueries({ queryKey: ["setup-status"] });
    await qc.invalidateQueries({ queryKey: ["github-repositories"] });
    if (failed.length === 0) {
      toast.success(`${ok} file(s) added`);
    } else {
      toast.warning(
        `${ok} added, ${failed.length} failed: ${failed
          .map(([name]) => name)
          .join(", ")}`,
      );
    }
    return { ok, failed };
  };
  const mutation = useMutation({
    mutationKey: SOURCE_MUTATION_KEY,
    mutationFn: ({
      files,
      mode,
      anchor,
    }: {
      files: File[];
      mode?: string;
      anchor?: string | null;
    }) => uploadAll(files, mode, anchor),
  });
  return {
    uploadAll: (files: File[], mode?: string, anchor?: string | null) =>
      mutation.mutateAsync({ files, mode, anchor }),
  };
}

export function usePatchSource() {
  const qc = useQueryClient();
  return useMutation({
    mutationKey: SOURCE_MUTATION_KEY,
    mutationFn: ({
      id,
      ...patch
    }: { id: string } & Partial<
      Pick<ProfileSource, "mode" | "anchor" | "primary">
    >) =>
      unwrap(
        api.PATCH("/api/profile/sources/{doc_id}", {
          params: { path: { doc_id: id } },
          body: patch,
        } as never),
      ) as Promise<ProfileSource>,
    onSuccess: () =>
      Promise.all([
        qc.invalidateQueries({ queryKey: ["profile-sources"] }),
        qc.invalidateQueries({ queryKey: ["setup-status"] }),
      ]),
    onError: (err: Error) => toast.error(err.message),
  });
}

export function useDeleteSource() {
  const qc = useQueryClient();
  return useMutation({
    mutationKey: SOURCE_MUTATION_KEY,
    mutationFn: (id: string) =>
      unwrap(
        api.DELETE("/api/profile/sources/{doc_id}", {
          params: { path: { doc_id: id }, query: { purge: true } },
        } as never),
      ),
    onSuccess: () =>
      toast.success(
        "Source removed. Rebuild your profile to update its facts.",
      ),
    onSettled: () =>
      Promise.all([
        qc.invalidateQueries({ queryKey: ["profile-sources"] }),
        qc.invalidateQueries({ queryKey: ["profile-source-exclusions"] }),
        qc.invalidateQueries({ queryKey: ["github-repositories"] }),
        qc.invalidateQueries({ queryKey: ["setup-status"] }),
      ]),
    onError: (err: Error) => toast.error(err.message),
  });
}

export function useAddNote() {
  const qc = useQueryClient();
  return useMutation({
    mutationKey: SOURCE_MUTATION_KEY,
    mutationFn: (body: NoteInput) =>
      unwrap(api.POST("/api/profile/sources/note", { body })),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["profile-sources"] });
      qc.invalidateQueries({ queryKey: ["setup-status"] });
      toast.success("Note added");
    },
    onError: (err: Error) => toast.error(err.message),
  });
}

export function useAddUrl() {
  const qc = useQueryClient();
  return useMutation({
    mutationKey: SOURCE_MUTATION_KEY,
    mutationFn: (body: UrlInput) =>
      unwrap(api.POST("/api/profile/sources/url", { body })),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["profile-sources"] });
      qc.invalidateQueries({ queryKey: ["setup-status"] });
      toast.success("Page added");
    },
    onError: (err: Error) => toast.error(err.message),
  });
}

export function useSyncGithub() {
  const { launch } = useLaunchRun();
  const active = useActiveRun("github-sync");
  const [launching, setLaunching] = useState(false);
  const runPending =
    active?.status === "queued" ||
    active?.status === "running" ||
    active?.status === "cancelling";
  return {
    mutate: () => {
      if (launching || runPending) return;
      setLaunching(true);
      void launch("github-sync", launchers.githubSync, [
        "profile-sources",
        "github-repositories",
        "setup-status",
      ]).finally(() => setLaunching(false));
    },
    isPending: launching || runPending,
  };
}

export function useReplaceSource() {
  const qc = useQueryClient();
  return useMutation({
    mutationKey: SOURCE_MUTATION_KEY,
    mutationFn: async ({ oldId, file }: { oldId: string; file: File }) => {
      const form = new FormData();
      form.append("file", file);
      const token = getToken();
      const resp = await fetch(
        `/api/profile/sources/${encodeURIComponent(oldId)}/file`,
        {
          method: "PUT",
          body: form,
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        },
      );
      const body = await resp.json();
      if (!resp.ok)
        throw new Error(body?.error?.message ?? "Replacement failed");
      return body as ProfileSource;
    },
    onSuccess: () =>
      toast.success(
        "Source replaced. Rebuild your profile to update its facts.",
      ),
    onSettled: () =>
      Promise.all([
        qc.invalidateQueries({ queryKey: ["profile-sources"] }),
        qc.invalidateQueries({ queryKey: ["github-repositories"] }),
        qc.invalidateQueries({ queryKey: ["setup-status"] }),
      ]),
    onError: (err: Error) => toast.error(err.message),
  });
}

export function useDownloadSource() {
  return useMutation({
    mutationFn: async (source: ProfileSource) => {
      const token = getToken();
      const resp = await fetch(
        `/api/profile/sources/${encodeURIComponent(source.id)}/file`,
        {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        },
      );
      if (!resp.ok) {
        const body = await resp.json();
        throw new Error(body?.error?.message ?? "Download failed");
      }
      const url = URL.createObjectURL(await resp.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = source.filename;
      document.body.append(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    },
    onError: (err: Error) => toast.error(err.message),
  });
}
