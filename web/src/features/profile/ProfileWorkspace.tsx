import { Button, buttonVariants } from "@/components/ui/button";
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import "@/i18n/profile-publication";
import { useIsMutating } from "@tanstack/react-query";
import {
  ArrowRight,
  FileText,
  FolderGit2,
  RefreshCw,
  Sparkles,
  Wrench,
} from "lucide-react";
import { useSearchParams } from "react-router-dom";

import { GuidedWorkspaceHeader } from "@/components/chat/GuidedWorkspaceHeader";
import { Badge } from "@/components/ui/badge";
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { TagListInput } from "@/components/ui/tag-list-input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { BuildReportPanel } from "@/features/profile-sources/BuildReportPanel";
import { SourceManager } from "@/features/profile-sources/SourceManager";
import { GithubRepositoryPicker } from "@/features/profile-sources/GithubRepositoryPicker";
import { GithubSyncReport } from "@/features/profile-sources/GithubSyncReport";
import {
  SOURCE_MUTATION_KEY,
  useGithubRepositories,
  useSyncGithub,
} from "@/features/profile-sources/use-sources";
import { useActiveRun } from "@/features/runs/use-active-run";
import { launchers, useLaunchRun } from "@/features/runs/use-launch-run";
import { SaveBar } from "@/features/settings/SaveBar";
import { SkillGroupsPanel } from "@/features/settings/SkillGroupsPanel";
import { SKILL_MUTATION_KEY } from "@/features/profile-skills/use-profile-skills";
import { useConfig, useSaveConfig } from "@/features/settings/use-config";
import { useDraft } from "@/features/settings/use-draft";
import { useSetupStatus } from "@/features/settings/use-setup-status";
import type { paths } from "@/lib/api/schema";
import { formatUserDateTime } from "@/lib/date-time";
import { validateTagDrafts } from "@/lib/tag-list-drafts";

type ProfileDoc =
  paths["/api/config/profile"]["get"]["responses"][200]["content"]["application/json"];
type ProfileDraft = Omit<ProfileDoc, "githubRepoLimit"> & {
  limitText: string;
};

function editableProfile(
  data: ProfileDoc | undefined,
): ProfileDraft | undefined {
  if (!data) return undefined;
  const { githubRepoLimit, ...rest } = data;
  return {
    ...rest,
    githubRepoAllow: rest.githubRepoAllow ?? [],
    githubRepoDeny: rest.githubRepoDeny ?? [],
    limitText: String(githubRepoLimit ?? 20),
  };
}

function savedProfile(draft: ProfileDraft): ProfileDoc {
  const { limitText, ...rest } = draft;
  return {
    ...rest,
    githubRepoLimit: Number(limitText),
  };
}

/**
 * The Profile workspace — step 1 of the job-hunting journey, promoted out of
 * Settings to a top-level destination. The coach (how you enrich the profile)
 * is the hero action; the two heavy configuration surfaces (Documents, Skills)
 * are split into tabs so nothing is stacked on one endless page.
 */
export function ProfileWorkspace() {
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = searchParams.get("tab") === "skills" ? "skills" : "documents";
  const { data, isError, refetch } = useConfig("/api/config/profile");
  const save = useSaveConfig("/api/config/profile");
  const { draft, setDraft, dirty, reset } = useDraft(
    editableProfile(data as ProfileDoc | undefined),
  );
  const [importPreferencesOpen, setImportPreferencesOpen] = useState(false);
  const [preferencesVersion, setPreferencesVersion] = useState(0);
  const preferences = useRef<HTMLDetailsElement>(null);
  const githubUsername = data?.githubUsername ?? null;
  const settingsKey = JSON.stringify(data);
  const canSuggestRepositories = !!githubUsername && draft?.githubUsername === githubUsername;
  const repositories = useGithubRepositories(
    githubUsername,
    settingsKey,
    activeTab === "documents" && importPreferencesOpen && canSuggestRepositories,
  );
  const setupStatus = useSetupStatus();
  const { launch } = useLaunchRun();
  const buildRun = useActiveRun("profile-build");
  const [launchingBuild, setLaunchingBuild] = useState(false);
  const building =
    launchingBuild ||
    (!!buildRun &&
      ["queued", "running", "cancelling"].includes(buildRun.status));
  const syncGithub = useSyncGithub();
  const skillRun = useActiveRun("profile-skills-rebuild");
  const skillMutations = useIsMutating({ mutationKey: SKILL_MUTATION_KEY });
  const sourceMutations = useIsMutating({ mutationKey: SOURCE_MUTATION_KEY });

  const setActiveTab = (value: string | null) => {
    const next = new URLSearchParams(searchParams);
    if (value === "skills") next.set("tab", "skills");
    else next.delete("tab");
    setSearchParams(next, { replace: true });
  };

  if (isError && !draft)
    return (
      <div
        role="alert"
        className="space-y-3 rounded-xl border border-destructive/30 p-4"
      >
        <p>Profile settings could not be loaded. Try again.</p>
        <Button variant="outline" onClick={() => void refetch()}>
          Try again
        </Button>
      </div>
    );
  if (!draft) return <Skeleton className="h-64 w-full" />;

  const { githubRepoAllow, githubRepoDeny, limitText } = draft;
  const repositoryOwner = draft.githubUsername?.trim().toLowerCase();
  const repositoryKey = (tag: string) => {
    const name = tag.trim().toLowerCase();
    return repositoryOwner && !name.includes("/") ? `${repositoryOwner}/${name}` : name;
  };
  const repositorySuggestions = canSuggestRepositories
    ? (repositories.data ?? []).map((repo) => ({ value: repo.fullName, label: repo.fullName }))
    : undefined;
  const repositorySearchMessage = repositories.isFetching
    ? t("tagList.repositories.loading")
    : repositories.isError ? t("tagList.repositories.unavailable") : undefined;
  const repositoryPlaceholder = t(canSuggestRepositories ? "tagList.repositories.search" : "tagList.repositories.name");
  const parsedLimit = Number(limitText);
  const limitValid =
    Number.isInteger(parsedLimit) && parsedLimit >= 1 && parsedLimit <= 100;
  const busy =
    building || syncGithub.isPending || save.isPending || sourceMutations > 0 || skillMutations > 0 || !!(skillRun && ["queued", "running", "cancelling"].includes(skillRun.status));
  const canRebuild = setupStatus.data?.profile.canRebuild ??
    (setupStatus.data?.profile.hasResume !== false);
  const buildDisabled = busy || dirty || !canRebuild;
  const rebuild = async () => {
    if (buildDisabled) return false;
    setLaunchingBuild(true);
    try {
      return await launch("profile-build", () => launchers.profileBuild(), [
        "setup-status",
        "profile-sources",
        "profile-skeleton",
        "profile-matrix",
        "profile-skills",
        "skill-cleanup",
        "suppressed-skills",
        "match-gap",
        "job",
        "triage",
        "shortlist",
        "pipeline",
      ]);
    } finally {
      setLaunchingBuild(false);
    }
  };
  const freshness = setupStatus.data?.profile.freshness ??
    (setupStatus.data?.profile.factsBuiltAt ? "unknown" : "missing");
  const freshnessKey = freshness === "refresh-needed" ? "pending" : freshness;

  return (
    <div className="flex flex-col gap-6">
      <GuidedWorkspaceHeader
        tone="coach"
        icon={<Sparkles />}
        title="Profile"
        meta={
          <Badge variant="outline" className="h-auto min-h-5 max-w-full whitespace-normal">
            {t(`profilePublication.${freshnessKey}`)}
          </Badge>
        }
        actions={
          <>
            <Button disabled={buildDisabled} onClick={() => void rebuild()}>
              {building ? (
                <Spinner data-icon="inline-start" />
              ) : (
                <Sparkles data-icon="inline-start" aria-hidden="true" />
              )}
              {building
                ? "Building…"
                : setupStatus.data?.profile.factsBuiltAt
                  ? "Rebuild profile"
                  : "Build profile"}
            </Button>
            <a
              className={buttonVariants({ variant: "outline" })}
              data-slot="button"
              href="/coach"
            >
              Open coach
              <ArrowRight data-icon="inline-end" aria-hidden="true" />
            </a>
          </>
        }
      />

      {freshness === "refresh-needed" || freshness === "unknown" ? (
        <p role="status" className="text-sm text-muted-foreground">
          {t(freshness === "refresh-needed" ? "profilePublication.pendingHelp" : "profilePublication.unknownHelp")}
        </p>
      ) : null}
      {setupStatus.data?.profile.publishedAt ? (
        <p className="text-sm text-muted-foreground">
          {t("profilePublication.published", { date: formatUserDateTime(setupStatus.data.profile.publishedAt) })}
        </p>
      ) : null}

      {dirty ? (
        <p role="status" className="text-sm text-muted-foreground">
          Save your GitHub changes before syncing or building. Your selected
          branches are not applied until saved.
        </p>
      ) : null}
      {building ? (
        <p role="status" className="text-sm text-muted-foreground">
          Building your profile from saved evidence. You can follow progress in
          the build report.
        </p>
      ) : null}

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="max-w-full flex-wrap group-data-horizontal/tabs:h-auto [&_button]:h-auto [&_button]:min-h-10">
          <TabsTrigger value="documents">
            <FileText data-icon="inline-start" aria-hidden="true" />
            Documents
          </TabsTrigger>
          <TabsTrigger value="skills">
            <Wrench data-icon="inline-start" aria-hidden="true" />
            Skills
          </TabsTrigger>
        </TabsList>

        <TabsContent value="documents" className="flex flex-col gap-4 pt-2">
          <SourceManager disabled={busy} onRefresh={rebuild} refreshDisabled={buildDisabled} />
          <section
            aria-label="GitHub projects"
            className="@container/github min-w-0 space-y-4 rounded-xl border border-border bg-card p-4 sm:p-5"
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0 space-y-1">
                <h2 className="flex items-center gap-2 text-lg font-semibold">
                  <FolderGit2 className="size-5" aria-hidden="true" />
                  GitHub projects
                </h2>
              </div>
              <Button
                variant="outline"
                className="h-auto min-h-10 max-w-full whitespace-normal"
                disabled={busy || dirty || !data?.githubUsername}
                onClick={() => syncGithub.mutate()}
              >
                {syncGithub.isPending ? (
                  <Spinner data-icon="inline-start" />
                ) : (
                  <RefreshCw data-icon="inline-start" aria-hidden="true" />
                )}
                Sync GitHub
              </Button>
            </div>
            <FieldGroup>
              <Field className="grid min-w-0 @3xl/github:grid-cols-[minmax(0,12rem)_minmax(0,24rem)] @3xl/github:items-center @3xl/github:gap-4">
                <FieldLabel htmlFor="githubUsername">
                  GitHub username
                </FieldLabel>
                <Input
                  id="githubUsername"
                  value={draft.githubUsername ?? ""}
                  disabled={busy}
                  onChange={(e) =>
                    setDraft({
                      ...draft,
                      githubUsername: e.target.value || null,
                    })
                  }
                />
              </Field>
            </FieldGroup>
            <GithubRepositoryPicker
              username={githubUsername}
              branches={draft.githubRepoBranches ?? {}}
              settingsKey={settingsKey}
              disabled={busy || draft.githubUsername !== data?.githubUsername}
              onChange={(branches) =>
                setDraft({ ...draft, githubRepoBranches: branches })
              }
            />
            <details
              ref={preferences}
              className="rounded-lg border border-border px-4"
              open={importPreferencesOpen}
              onToggle={(event) => setImportPreferencesOpen(event.currentTarget.open)}
            >
              <summary className="min-h-11 cursor-pointer py-3 text-sm font-medium outline-none focus-visible:ring-2 focus-visible:ring-ring">
                {t("tagList.repositories.preferences")}
              </summary>
              <FieldGroup key={preferencesVersion} className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,15rem),1fr))] gap-4 pb-4 pt-2">
                <TagListInput
                  id="githubRepoAllow"
                  label={t("tagList.repositories.include")}
                  disabled={busy}
                  value={githubRepoAllow ?? []}
                  placeholder={repositoryPlaceholder}
                  description={t("tagList.repositories.includeHelp")}
                  suggestions={repositorySuggestions}
                  getKey={repositoryKey}
                  emptySuggestions={repositorySearchMessage}
                  onChange={(values) => setDraft({ ...draft, githubRepoAllow: values })}
                />
                <TagListInput
                  id="githubRepoDeny"
                  label={t("tagList.repositories.exclude")}
                  disabled={busy}
                  value={githubRepoDeny ?? []}
                  placeholder={repositoryPlaceholder}
                  description={t("tagList.repositories.excludeHelp")}
                  suggestions={repositorySuggestions}
                  getKey={repositoryKey}
                  emptySuggestions={repositorySearchMessage}
                  onChange={(values) => setDraft({ ...draft, githubRepoDeny: values })}
                />
                <Field className="min-w-0">
                  <FieldLabel htmlFor="githubRepoLimit">
                    {t("tagList.repositories.limit")}
                  </FieldLabel>
                  <Input
                    id="githubRepoLimit"
                    disabled={busy}
                    type="number"
                    min={1}
                    max={100}
                    aria-invalid={!limitValid}
                    aria-describedby="githubRepoLimit-help"
                    value={limitText}
                    onChange={(event) => {
                      setDraft({ ...draft, limitText: event.target.value });
                    }}
                  />
                  <FieldDescription id="githubRepoLimit-help">
                    {limitValid
                      ? t("tagList.repositories.limitHelp")
                      : t("tagList.repositories.invalidLimit")}
                  </FieldDescription>
                </Field>
              </FieldGroup>
            </details>
            <SaveBar
              dirty={dirty}
              saving={save.isPending}
              canSave={limitValid && !busy}
              sticky={false}
              onSave={() => {
                if (validateTagDrafts(preferences.current)) {
                  save.mutate(savedProfile(draft), {
                    onSuccess: (saved) => setDraft(editableProfile(saved) ?? null),
                  });
                }
              }}
              onDiscard={() => {
                reset();
                setPreferencesVersion((version) => version + 1);
              }}
            />
            <GithubSyncReport />
          </section>
          <BuildReportPanel />
        </TabsContent>

        <TabsContent value="skills" className="flex flex-col gap-6 pt-2">
          <SkillGroupsPanel disabled={busy} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
