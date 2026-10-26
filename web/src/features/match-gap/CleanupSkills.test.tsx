import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

import type { components } from "@/lib/api/schema";
import { changeLanguage } from "@/i18n";
import { server } from "@/test/server";
import { CleanupSkills } from "./CleanupSkills";
import { MATCH_GAP_QUERY_KEY } from "./use-match-gap";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const data: components["schemas"]["MatchGapOut"] = {
  targetTotal: 1,
  clustersStale: false,
  taxonomyAlgorithmVersion: "embedding-taxonomy-v1",
  taxonomyMaintenanceDue: false,
  taxonomyRevision: "fixture",
  taxonomyUndoAvailable: false,
  unassignedCount: 0,
  jobs: [],
  edges: [],
  domains: [],
  categories: [],
  skills: ["Python", "2 years"].map((skill) => ({
    key: skill.toLowerCase(),
    skill,
    covered: false,
    coverage: "gap",
    members: {},
    must: 1,
    nice: 0,
    tech: 0,
    jobCount: 1,
  })),
  cleanupCandidates: [
    { key: "2 years", reason: "Years-of-experience requirement" },
  ],
};

function setup() {
  const client = new QueryClient({
    defaultOptions: { mutations: { retry: false } },
  });
  const view = render(
    <QueryClientProvider client={client}>
      <CleanupSkills data={data} />
    </QueryClientProvider>,
  );
  return { client, ...view };
}

it.each(["en", "zh-CN"] as const)("reviews candidates and excludes only checked entries in %s", async (language) => {
  await changeLanguage(language);
  const chinese = language === "zh-CN";
  const calls: unknown[] = [];
  const fresh = {
    ...data,
    skills: data.skills.slice(0, 1),
    cleanupCandidates: [],
  };
  server.use(
    http.post("/api/taxonomy/discard-skills", async ({ request }) => {
      calls.push(await request.json());
      return HttpResponse.json(fresh);
    }),
  );
  const { client, baseElement } = setup();
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: chinese ? "清理技能" : "Clean up skills" }));
  expect(
    screen.getByText(chinese ? "工作年限要求" : "Years-of-experience requirement"),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("checkbox", { name: chinese ? "排除 Python" : "Discard Python" }),
  ).not.toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: chinese ? "排除所选条目（0）" : "Discard selected (0)" }),
  ).toBeDisabled();
  expect(calls).toEqual([]);
  expect((await axe(baseElement)).violations).toEqual([]);
  await user.click(screen.getByRole("checkbox", { name: chinese ? "排除 2 years" : "Discard 2 years" }));
  await user.click(
    screen.getByRole("button", { name: chinese ? "排除所选条目（1）" : "Discard selected (1)" }),
  );
  await waitFor(() =>
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
  );
  expect(calls).toEqual([{ skillKeys: ["2 years"] }]);
  expect(client.getQueryData(MATCH_GAP_QUERY_KEY)).toEqual(fresh);
});

it("allows searching other entries and keeps the selection after a failed discard", async () => {
  server.use(
    http.post("/api/taxonomy/discard-skills", () =>
      HttpResponse.json(
        {
          error: { code: "FAILURE", message: "Try again" },
        },
        { status: 500 },
      ),
    ),
  );
  setup();
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Clean up skills" }));
  await user.click(screen.getByRole("button", { name: "All skill entries" }));
  await user.type(
    screen.getByRole("textbox", { name: "Search cleanup entries" }),
    "Python",
  );
  await user.click(screen.getByRole("button", { name: "Select visible" }));
  await user.click(
    screen.getByRole("button", { name: "Discard selected (1)" }),
  );
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "Discard selected (1)" }),
    ).toBeEnabled(),
  );
  expect(
    screen.getByRole("checkbox", { name: "Discard Python" }),
  ).toBeChecked();
  expect(
    screen.queryByRole("checkbox", { name: "Discard 2 years" }),
  ).not.toBeInTheDocument();
});
