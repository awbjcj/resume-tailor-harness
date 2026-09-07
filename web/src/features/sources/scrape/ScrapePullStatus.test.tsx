import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { server } from "@/test/server";
import { withQueryClient } from "@/test/utils";
import { ScrapePullStatus } from "./ScrapePullStatus";

describe("public source pull status", () => {
  it("shows the terminal outcome and every pull counter", async () => {
    server.use(
      http.get("/api/runs/pull-run", () =>
        HttpResponse.json({
          state: "done",
          result: {
            terminalReason: "partial_limit",
            discovered: 12,
            inspected: 8,
            imported: 4,
            duplicate: 2,
            filtered: 1,
            reviewNeeded: 2,
            failed: 1,
            messages: [],
          },
        }),
      ),
    );

    render(<ScrapePullStatus runId="pull-run" />, {
      wrapper: withQueryClient,
    });

    expect(await screen.findByText("Pull outcome: partial limit")).toBeVisible();
    expect(screen.getByText("12 discovered · 8 inspected · 4 imported")).toBeVisible();
    expect(
      screen.getByText("2 duplicates · 1 filtered · 2 need review · 1 failed"),
    ).toBeVisible();
  });
});
