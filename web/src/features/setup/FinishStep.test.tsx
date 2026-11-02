import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

import { changeLanguage } from "@/i18n";
import { useRunStore } from "@/lib/runs/store";
import { server } from "@/test/server";
import { withQueryClient } from "@/test/utils";
import { FinishStep } from "./FinishStep";

describe("FinishStep", () => {
  afterEach(() => useRunStore.setState({ runs: {} }));

  it("does not let an earlier successful run hide newly pending evidence", async () => {
    server.use(http.get("*/api/setup/status", () => HttpResponse.json({
      secrets: { anthropicKey: true, anyLlmKey: true },
      profile: { documentCount: 2, hasResume: true, canRebuild: true, factsBuiltAt: "2026-11-01", freshness: "refresh-needed", pendingSourceCount: 1 },
      search: { configured: true }, sources: { enabledCount: 1 }, complete: true,
    })));
    useRunStore.setState({ runs: { old: { runId: "old", kind: "profile-build", status: "succeeded", percent: 100, phase: "Complete", current: 1, total: 1, etaText: null, result: { experiences: 3, projects: 2 } } } });
    await changeLanguage("en");
    render(<MemoryRouter><FinishStep /></MemoryRouter>, { wrapper: withQueryClient });
    expect(await screen.findByRole("button", { name: "Build profile" })).toBeEnabled();
    expect(screen.queryByText(/3 experiences/)).not.toBeInTheDocument();
  });

  it("labels successful extraction counts as completion rather than a timestamp in Chinese", async () => {
    server.use(
      http.get("*/api/setup/status", () =>
        HttpResponse.json({
          secrets: { anthropicKey: true, anyLlmKey: true },
          profile: {
            documentCount: 1,
            hasResume: true,
            factsBuiltAt: "2026-10-02T18:00:00Z",
            githubUsername: null,
          },
          search: { configured: true },
          sources: { enabledCount: 1 },
          complete: true,
        }),
      ),
    );
    useRunStore.setState({
      runs: {
        "profile-build-1": {
          runId: "profile-build-1",
          kind: "profile-build",
          status: "succeeded",
          percent: 100,
          phase: "Complete",
          current: 1,
          total: 1,
          etaText: null,
          result: { experiences: 3, projects: 2 },
        },
      },
    });
    await changeLanguage("zh-CN");
    render(
      <MemoryRouter>
        <FinishStep />
      </MemoryRouter>,
      { wrapper: withQueryClient },
    );

    expect(
      screen.getByText(/个人资料已生成：\s*3\s*经历，\s*2\s*个项目已提取。/),
    ).toBeInTheDocument();
    expect(screen.queryByText(/个人资料生成时间/)).toBeNull();
  });
});
