import { beforeEach, expect, it } from "vitest";

import {
  DEFAULT_INVALIDATE,
  forgetInvalidation,
  invalidationKeys,
  rememberInvalidation,
  resetInvalidationForTests,
} from "./invalidation";

beforeEach(() => resetInvalidationForTests());

it("falls back to the default keys for an unknown kind", () => {
  expect(invalidationKeys("r1", "somethingNew")).toEqual([...DEFAULT_INVALIDATE]);
});

it("uses the per-kind map for a run it never saw launched", () => {
  expect(invalidationKeys("r1", "refreshClusters")).toEqual(["match-gap"]);
  expect(invalidationKeys("r2", "profile-build")).toEqual([
    "profile-sources",
    "match-gap",
    "setup-status",
    "profile-matrix",
    "profile-skills",
    "skill-cleanup",
    "suppressed-skills",
    "job",
    "shortlist",
    "pipeline",
    "triage",
  ]);
});

it("prefers a remembered per-run override", () => {
  rememberInvalidation("r1", ["setup-status"]);
  expect(invalidationKeys("r1", "profile-build")).toEqual(["setup-status"]);
});

it("forgets an override so a recycled id cannot inherit it", () => {
  rememberInvalidation("r1", ["setup-status"]);
  forgetInvalidation("r1");
  expect(invalidationKeys("r1", "profile-build")).toEqual([
    "profile-sources",
    "match-gap",
    "setup-status",
    "profile-matrix",
    "profile-skills",
    "skill-cleanup",
    "suppressed-skills",
    "job",
    "shortlist",
    "pipeline",
    "triage",
  ]);
});

it("returns a fresh array so callers cannot mutate the shared tables", () => {
  const first = invalidationKeys("r1", "refreshClusters");
  first.push("mutated");
  expect(invalidationKeys("r2", "refreshClusters")).toEqual(["match-gap"]);
});

it("refreshes skill CRUD surfaces after a skill rebuild discovered on reload", () => {
  expect(invalidationKeys("r1", "profile-skills-rebuild")).toEqual(expect.arrayContaining(["profile-matrix", "profile-skills", "skill-cleanup", "suppressed-skills", "job", "match-gap"]));
});
