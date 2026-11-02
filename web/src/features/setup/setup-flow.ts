import type { SetupStatus } from "@/features/settings/use-setup-status";

export const STEPS = [
  { slug: "keys", label: "Keys", done: (s: SetupStatus) => s.secrets.anyLlmKey },
  { slug: "documents", label: "Documents", done: (s: SetupStatus) => s.profile.hasResume || s.profile.canRebuild },
  { slug: "search", label: "Search", done: (s: SetupStatus) => s.search.configured },
  { slug: "sources", label: "Sources", done: (s: SetupStatus) => s.sources.enabledCount > 0 },
] as const;

export function setupSteps(destination = "/") {
  const path = destination.split("?")[0];
  return /^\/(pipeline|shortlist|triage)(\/|$)/.test(path)
    ? STEPS.filter((step) => step.slug === "keys" || step.slug === "documents")
    : [...STEPS];
}

export function firstIncompleteStep(status: SetupStatus, destination = "/"): string {
  return setupSteps(destination).find((step) => !step.done(status))?.slug ?? "finish";
}
