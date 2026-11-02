import { describe, expect, it } from "vitest";

import { firstIncompleteStep, STEPS } from "./SetupWizard";
import type { SetupStatus } from "@/features/settings/use-setup-status";

const status = (over: Omit<Partial<SetupStatus>, "profile"> & { profile?: Partial<SetupStatus["profile"]> }): SetupStatus => ({
  secrets: { anthropicKey: false, anyLlmKey: false },
  search: { configured: false }, sources: { enabledCount: 0 }, complete: false,
  ...over,
  profile: { documentCount: 0, hasResume: false, canRebuild: false, factsBuiltAt: null, githubUsername: null, freshness: "missing", pendingSourceCount: 0, ...over.profile },
});

describe("firstIncompleteStep", () => {
  it("starts at keys on a fresh install", () => {
    expect(firstIncompleteStep(status({}))).toBe("keys");
  });
  it("resumes at search when keys and documents are done", () => {
    expect(
      firstIncompleteStep(status({
        secrets: { anthropicKey: true, anyLlmKey: true },
        profile: { documentCount: 1, hasResume: true, factsBuiltAt: null, githubUsername: null },
      })),
    ).toBe("search");
  });
  it("lands on finish when every step is done", () => {
    expect(
      firstIncompleteStep(status({
        secrets: { anthropicKey: true, anyLlmKey: true },
        profile: { documentCount: 1, hasResume: true, factsBuiltAt: null, githubUsername: null },
        search: { configured: true }, sources: { enabledCount: 2 },
      })),
    ).toBe("finish");
  });

  it("accepts conversational profile evidence in place of a resume upload", () => {
    expect(firstIncompleteStep(status({
      secrets: { anthropicKey: true, anyLlmKey: true },
      profile: { documentCount: 0, hasResume: false, canRebuild: true, factsBuiltAt: "2026-11-01", githubUsername: null },
    }))).toBe("search");
  });
  it("exposes exactly four steps", () => {
    expect(STEPS.map((s) => s.slug)).toEqual(["keys", "documents", "search", "sources"]);
  });
});
