import { Button, buttonVariants } from "@/components/ui/button";
import { useState } from "react";
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { BuildReportPanel } from "@/features/profile-sources/BuildReportPanel";
import { SourceManager } from "@/features/profile-sources/SourceManager";
import { GithubRepositoryPicker } from "@/features/profile-sources/GithubRepositoryPicker";
import { GithubSyncReport } from "@/features/profile-sources/GithubSyncReport";
import {
  SOURCE_MUTATION_KEY,
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

type ProfileDoc =
  paths["/api/config/profile"]["get"]["responses"][200]["content"]["application/json"];
type ProfileDraft = Omit<
  ProfileDoc,
  "githubRepoAllow" | "githubRepoDeny" | "githubRepoLimit"
> & {
  allowText: string;
  denyText: string;
  limitText: string;
};

function editableProfile(
  data: ProfileDoc | undefined,
): ProfileDraft | undefined {
  if (!data) return undefined;
  const { githubRepoAllow, githubRepoDeny, githubRepoLimit, ...rest } = data;
  return {
    ...rest,
    allowText: (githubRepoAllow ?? []).join(", "),
    denyText: (githubRepoDeny ?? []).join(", "),
    limitText: String(githubRepoLimit ?? 20),
  };
}

function savedProfile(draft: ProfileDraft): ProfileDoc {
  const { allowText, denyText, limitText, ...rest } = draft;
  return {
    ...rest,
    githubRepoAllow: parseRepoList(allowText),
    githubRepoDeny: parseRepoList(denyText),
    githubRepoLimit: Number(limitText),
  };
}

function parseRepoList(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function factsStatusText(builtAt: string | null | undefined): string {
  if (!builtAt) return "Not built yet";
  return `Profile built ${formatUserDateTime(builtAt)}`;
}

/**
 * The Profile workspace — step 1 of the job-hunting journey, promoted out of
 * Settings to a top-level destination. The coach (how you enrich the profile)
 * is the hero action; the two heavy configuration surfaces (Documents, Skills)
 * are split into tabs so nothing is stacked on one endless page.
 */
export function ProfileWorkspace() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { data, isError, refetch } = useConfig("/api/config/profile");
  const save = useSaveConfig("/api/config/profile");
  const { draft, setDraft, dirty, reset } = useDraft(
    editableProfile(data as ProfileDoc | undefined),
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
  const activeTab =
    searchParams.get("tab") === "skills" ? "skills" : "documents";

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

  const { allowText, denyText, limitText } = draft;
  const parsedLimit = Number(limitText);
  const limitValid =
    Number.isInteger(parsedLimit) && parsedLimit >= 1 && parsedLimit <= 100;
  const busy =
    building || syncGithub.isPending || save.isPending || sourceMutations > 0 || skillMutations > 0 || !!(skillRun && ["queued", "running", "cancelling"].includes(skillRun.status));
  const canRebuild = setupStatus.data?.profile.canRebuild ??
    (setupStatus.data?.profile.hasResume !== false);
  const buildDisabled = busy || dirty || !canRebuild;
  const rebuild = () => {
    if (buildDisabled) return;
    setLaunchingBuild(true);
    void launch("profile-build", () => launchers.profileBuild(), [
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
    ]).finally(() => setLaunchingBuild(false));
  };

  return (
    <div className="flex flex-col gap-6">
      <GuidedWorkspaceHeader
        tone="coach"
        icon={<Sparkles />}
        eyebrow="Step 1 · Your profile"
        title="Profile"
        description="Build your profile from your resume and project evidence to tailor your applications."
        meta={
          <Badge variant="outline" className="h-auto min-h-5 max-w-full whitespace-normal">
            {factsStatusText(setupStatus.data?.profile.factsBuiltAt)}
          </Badge>
        }
        actions={
          <>
            <Button disabled={buildDisabled} onClick={rebuild}>
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

      <ol
        aria-label="Profile building steps"
        className="grid min-w-0 grid-cols-[repeat(auto-fit,minmax(min(100%,15rem),1fr))] gap-3 [overflow-wrap:anywhere]"
      >
        <li className="flex items-start gap-3 rounded-lg border border-border px-4 py-3">
          <span className="shrink-0 font-mono text-sm tabular-nums text-muted-foreground">01</span>
          <div>
            <p className="text-sm font-medium">Add your evidence</p>
            <p className="text-sm text-muted-foreground">
              Resume and supporting documents
            </p>
          </div>
        </li>
        <li className="flex items-start gap-3 rounded-lg border border-border px-4 py-3">
          <span className="shrink-0 font-mono text-sm tabular-nums text-muted-foreground">02</span>
          <div>
            <p className="text-sm font-medium">Choose GitHub branches (optional)</p>
            <p className="text-sm text-muted-foreground">
              Choose the branch with each project's documents
            </p>
          </div>
        </li>
        <li className="flex items-start gap-3 rounded-lg border border-border px-4 py-3">
          <span className="shrink-0 font-mono text-sm tabular-nums text-muted-foreground">03</span>
          <div>
            <p className="text-sm font-medium">Build your profile</p>
            <p className="text-sm text-muted-foreground">
              Extract facts from your saved sources
            </p>
          </div>
        </li>
      </ol>
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

        <TabsContent value="documents" className="flex flex-col gap-6 pt-2">
          <SourceManager disabled={busy} />
          <section
            aria-label="GitHub projects"
            className="min-w-0 space-y-5 rounded-xl border border-border bg-card p-4 sm:p-5"
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0 space-y-1">
                <h2 className="flex items-center gap-2 text-lg font-semibold">
                  <FolderGit2 className="size-5" aria-hidden="true" />
                  GitHub projects
                </h2>
                <p className="max-w-prose text-sm text-muted-foreground">
                  Choose a branch for each repository. Sync saves project
                  documents; building extracts facts for your profile.
                </p>
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
              <Field>
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
                <FieldDescription>
                  Optional. Save your username before loading repositories.
                  Builds also sync your saved branch choices.
                </FieldDescription>
              </Field>
            </FieldGroup>
            <GithubRepositoryPicker
              username={data?.githubUsername ?? null}
              branches={draft.githubRepoBranches ?? {}}
              settingsKey={JSON.stringify(data)}
              disabled={busy || draft.githubUsername !== data?.githubUsername}
              onChange={(branches) =>
                setDraft({ ...draft, githubRepoBranches: branches })
              }
            />
            <details className="rounded-lg border border-border px-4">
              <summary className="min-h-11 cursor-pointer py-3 text-sm font-medium outline-none focus-visible:ring-2 focus-visible:ring-ring">
                Import preferences
              </summary>
              <FieldGroup className="pb-4 pt-2">
                <Field>
                  <FieldLabel htmlFor="githubRepoAllow">
                    Always include repositories
                  </FieldLabel>
                  <Input
                    id="githubRepoAllow"
                    disabled={busy}
                    value={allowText}
                    placeholder="portfolio, flagship-project"
                    onChange={(event) => {
                      setDraft({ ...draft, allowText: event.target.value });
                    }}
                  />
                  <FieldDescription>
                    Comma-separated repository names that bypass ranking.
                  </FieldDescription>
                </Field>
                <Field>
                  <FieldLabel htmlFor="githubRepoDeny">
                    Exclude repositories
                  </FieldLabel>
                  <Input
                    id="githubRepoDeny"
                    disabled={busy}
                    value={denyText}
                    placeholder="archive, experiments"
                    onChange={(event) => {
                      setDraft({ ...draft, denyText: event.target.value });
                    }}
                  />
                  <FieldDescription>
                    Comma-separated repository names that are never harvested.
                  </FieldDescription>
                </Field>
                <Field>
                  <FieldLabel htmlFor="githubRepoLimit">
                    Repository limit
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
                      ? "Maximum ranked repositories to import, from 1 to 100."
                      : "Enter a whole number from 1 to 100 to save."}
                  </FieldDescription>
                </Field>
              </FieldGroup>
            </details>
            <SaveBar
              dirty={dirty}
              saving={save.isPending}
              canSave={limitValid && !busy}
              sticky={false}
              onSave={() =>
                save.mutate(savedProfile(draft), {
                  onSuccess: (saved) =>
                    setDraft(editableProfile(saved) ?? null),
                })
              }
              onDiscard={reset}
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
