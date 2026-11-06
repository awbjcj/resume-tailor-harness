import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { GitBranch, RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";

import { api, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { ListSearch } from "@/components/ui/list-search";
import { ListSection } from "@/components/ui/list-section";
import { SearchableSelect } from "@/components/ui/searchable-select";
import { listSearch } from "@/lib/list-search";
import { useGithubRepositories } from "./use-sources";

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
  const { t } = useTranslation();
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
    <li className="grid min-w-0 items-start gap-x-6 gap-y-2 py-3 @xl/repositories:grid-cols-[minmax(0,1fr)_minmax(12rem,18rem)]">
      <div className="flex min-w-0 flex-col justify-center gap-1 @xl/repositories:min-h-11">
        <span className="min-w-0 font-medium [overflow-wrap:anywhere]">{repo.fullName}</span>
        {repo.uploadedOverride ? (
          <p className="text-sm text-muted-foreground">
            An uploaded dossier takes priority over synced files for this
            repository.
          </p>
        ) : null}
      </div>
      <div className="min-w-0 space-y-2">
        <SearchableSelect
          label={t("longLists.branchFor", { name: repo.fullName })}
          className="min-h-11"
          value={value || DEFAULT_BRANCH}
          disabled={disabled}
          searchLabel={t("longLists.searchBranches")}
          loadingLabel={branches.isFetching ? t("longLists.loadingBranches") : undefined}
          onOpenChange={(open) => { if (open) setLoad(true); }}
          onChange={(selected) => onChange(selected === DEFAULT_BRANCH ? "" : selected)}
          groups={[
            {
              id: "default-branch",
              items: [{
                value: DEFAULT_BRANCH,
                label: repo.defaultBranch ? t("longLists.defaultNamedBranch", { branch: repo.defaultBranch }) : t("longLists.defaultBranch"),
              }],
            },
            { id: "branches", label: t("longLists.branches"), items: options.map((branch) => ({ value: branch, label: branch })) },
          ]}
        />
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
  const { t } = useTranslation();
  const [load, setLoad] = useState(false);
  const [search, setSearch] = useState("");
  const repositories = useGithubRepositories(username, settingsKey, load);
  const all = repositories.data ?? [];
  const matches = listSearch(search);
  const sections = [
    { included: true, label: t("longLists.includedRepositories") },
    { included: false, label: t("longLists.excludedRepositories") },
  ].map(({ included, label }) => ({
    included,
    label,
    rows: all.filter((repo) => Boolean(repo.included) === included && matches(
      repo.fullName, repo.defaultBranch, branches[repo.fullName.toLowerCase()] ?? branches[repo.name.toLowerCase()], label,
    )),
  }));
  const shown = sections.reduce((count, section) => count + section.rows.length, 0);
  return (
    <div className="@container/repositories min-w-0 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="font-medium">Repository branches</h3>
        </div>
        <Button
          variant="outline"
          className="h-auto min-h-11 max-w-full whitespace-normal text-left"
          disabled={!username || disabled || (load && repositories.isFetching)}
          onClick={() => {
            setLoad(true);
            if (load) void repositories.refetch();
          }}
        >
          {load && repositories.isFetching ? (
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
      {load && repositories.isLoading ? <Skeleton className="h-24 w-full" /> : null}
      {load && repositories.isError ? (
        <p role="alert" className="text-sm text-destructive">
          Could not load repositories. Check your saved username and GitHub
          access, then refresh.
        </p>
      ) : null}
      {load && repositories.data?.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No repositories found for this username.
        </p>
      ) : null}
      {load && repositories.data?.length ? (
        <div className="space-y-2">
          <ListSearch value={search} onChange={setSearch} aria-label={t("longLists.searchRepositories")} placeholder={t("longLists.searchRepositories")} />
          <p role="status" className="text-sm text-muted-foreground empty:sr-only">
            {search.trim() ? (shown ? t("longLists.results", { shown, total: all.length }) : t("longLists.noMatches")) : null}
          </p>
          {sections.map(({ included, label, rows }) => rows.length ? (
            <ListSection key={String(included)} label={label} count={rows.length} query={search.trim()} defaultOpen={all.length <= 10} className="rounded-lg border bg-muted/20">
              <p className="border-t px-3 pt-2 text-sm text-muted-foreground sm:px-4">
                {included
                  ? "Your selection will be used in the next sync or profile build."
                  : 'To sync this branch, add the repository to "Always include repositories" and remove any exclusions for it.'}
              </p>
              <ul className="divide-y px-3 sm:px-4">
                {rows.map((repo) => (
                  <RepositoryBranch
                    key={repo.fullName}
                    repo={repo}
                    disabled={disabled}
                    value={branches[repo.fullName.toLowerCase()] ?? branches[repo.name.toLowerCase()] ?? ""}
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
            </ListSection>
          ) : null)}
        </div>
      ) : null}
    </div>
  );
}
