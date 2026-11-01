import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { GitBranch, RefreshCw } from "lucide-react";

import { api, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

type Repository = components["schemas"]["GithubRepositoryOut"];
const DEFAULT_BRANCH = ":default";

function RepositoryBranch({
  repo,
  value,
  disabled,
  onChange,
}: {
  repo: Repository;
  value: string;
  disabled: boolean;
  onChange: (branch: string) => void;
}) {
  const [load, setLoad] = useState(false);
  const branches = useQuery({
    queryKey: ["github-branches", repo.owner, repo.name],
    enabled: load,
    staleTime: 60_000,
    retry: false,
    queryFn: () =>
      unwrap(
        api.GET("/api/profile/github/repositories/{owner}/{repo}/branches", {
          params: { path: { owner: repo.owner, repo: repo.name } },
        }),
      ),
  });
  const options = [
    ...new Set([...(branches.data ?? []), ...(value ? [value] : [])]),
  ];
  return (
    <li className="grid min-w-0 gap-x-6 gap-y-3 border-t border-border py-3 @3xl/repositories:grid-cols-[minmax(0,1fr)_minmax(14rem,20rem)] @3xl/repositories:items-center">
      <div className="min-w-0 space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="min-w-0 font-medium [overflow-wrap:anywhere]">
            {repo.fullName}
          </span>
          <Badge
            variant={repo.included ? "secondary" : "outline"}
            className="h-auto min-h-5 max-w-full whitespace-normal text-left"
          >
            {repo.included ? "Included" : "Not selected for sync"}
          </Badge>
        </div>
        <p className="text-sm text-muted-foreground">
          {repo.included
            ? "Your selection will be used in the next sync or profile build."
            : 'To sync this branch, add the repository to "Always include repositories" and remove any exclusions for it.'}
        </p>
        {repo.uploadedOverride ? (
          <p className="text-sm text-muted-foreground">
            An uploaded dossier takes priority over synced files for this
            repository.
          </p>
        ) : null}
      </div>
      <div className="min-w-0 space-y-2">
        <label
          className="sr-only"
          htmlFor={`branch-${repo.fullName}`}
        >
          {`Branch for ${repo.fullName}`}
        </label>
        <Select
          value={value || DEFAULT_BRANCH}
          disabled={disabled}
          onOpenChange={(open) => {
            if (open) setLoad(true);
          }}
          onValueChange={(selected) =>
            onChange(selected === DEFAULT_BRANCH ? "" : (selected ?? ""))
          }
        >
          <SelectTrigger
            id={`branch-${repo.fullName}`}
            style={{ height: "auto" }}
            className="min-h-11 w-full min-w-0 whitespace-normal [&_[data-slot=select-value]]:line-clamp-none"
          >
            <GitBranch
              className="size-4 text-muted-foreground"
              aria-hidden="true"
            />
            <SelectValue className="min-w-0 [overflow-wrap:anywhere]">
              {value ||
                (repo.defaultBranch
                  ? `Default (${repo.defaultBranch})`
                  : "Default branch")}
            </SelectValue>
          </SelectTrigger>
          <SelectContent
            alignItemWithTrigger={false}
            className="max-w-[calc(100vw-2rem)] data-open:animate-none data-closed:animate-none"
          >
            <SelectItem value={DEFAULT_BRANCH}>
              {repo.defaultBranch
                ? `Default (${repo.defaultBranch})`
                : "Default branch"}
            </SelectItem>
            {branches.isFetching ? (
              <div
                role="status"
                className="flex items-center gap-2 px-3 py-2 text-sm text-muted-foreground"
              >
                <Spinner />
                Loading branches…
              </div>
            ) : null}
            {options.map((branch) => (
              <SelectItem
                key={branch}
                value={branch}
                className="[&>div]:min-w-0 [&>div]:shrink"
              >
                <span className="whitespace-normal [overflow-wrap:anywhere]">
                  {branch}
                </span>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {branches.isError ? (
          <div className="space-y-2">
            <p role="alert" className="text-sm text-destructive">
              Could not load branches. Check repository access and try again.
            </p>
            <Button
              variant="outline"
              disabled={branches.isFetching || disabled}
              onClick={() => void branches.refetch()}
            >
              Retry branches
            </Button>
          </div>
        ) : null}
      </div>
    </li>
  );
}

export function GithubRepositoryPicker({
  username,
  branches,
  settingsKey,
  disabled,
  onChange,
}: {
  username: string | null;
  branches: Record<string, string>;
  settingsKey: string;
  disabled: boolean;
  onChange: (branches: Record<string, string>) => void;
}) {
  const [load, setLoad] = useState(false);
  const repositories = useQuery({
    queryKey: ["github-repositories", username, settingsKey],
    enabled: load && !!username,
    retry: false,
    staleTime: 60_000,
    queryFn: () => unwrap(api.GET("/api/profile/github/repositories")),
  });
  return (
    <div className="@container/repositories min-w-0 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="font-medium">Repository branches</h3>
          <p className="text-sm text-muted-foreground">
            Use the default branch, or choose the branch with your project
            documents.
          </p>
        </div>
        <Button
          variant="outline"
          className="h-auto min-h-11 max-w-full whitespace-normal text-left"
          disabled={!username || disabled || repositories.isFetching}
          onClick={() => {
            setLoad(true);
            if (load) void repositories.refetch();
          }}
        >
          {repositories.isFetching ? (
            <Spinner data-icon="inline-start" />
          ) : load ? (
            <RefreshCw data-icon="inline-start" aria-hidden="true" />
          ) : (
            <GitBranch data-icon="inline-start" aria-hidden="true" />
          )}
          {load ? "Refresh repositories" : "Choose repository branches"}
        </Button>
      </div>
      {!username ? (
        <p className="text-sm text-muted-foreground">
          Save your GitHub username to load repositories and their branches.
        </p>
      ) : null}
      {repositories.isLoading ? <Skeleton className="h-24 w-full" /> : null}
      {repositories.isError ? (
        <p role="alert" className="text-sm text-destructive">
          Could not load repositories. Check your saved username and GitHub
          access, then refresh.
        </p>
      ) : null}
      {repositories.data?.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No repositories found for this username.
        </p>
      ) : null}
      {repositories.data?.length ? (
        <ul>
          {repositories.data.map((repo) => (
            <RepositoryBranch
              key={repo.fullName}
              repo={repo}
              disabled={disabled}
              value={
                branches[repo.fullName.toLowerCase()] ??
                branches[repo.name.toLowerCase()] ??
                ""
              }
              onChange={(branch) => {
                const next = { ...branches };
                delete next[repo.name.toLowerCase()];
                if (branch) next[repo.fullName.toLowerCase()] = branch;
                else delete next[repo.fullName.toLowerCase()];
                onChange(next);
              }}
            />
          ))}
        </ul>
      ) : null}
    </div>
  );
}
