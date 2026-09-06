import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "@/test/server";
import { withQueryClient } from "@/test/utils";
import { SourceCorrections } from "./SourceCorrections";

describe("persistent source corrections", () => {
  it("saves an explicit unknown with the current field revision", async () => {
    let submitted: unknown;
    server.use(
      http.get("/api/jobs/1/source-observations", () =>
        HttpResponse.json([
          {
            id: "one",
            sourceId: "source",
            jobKey: "key",
            revision: 1,
            facts: {
              sourceUrl: "https://example.com/1",
              remotePolicy: "remote",
            },
          },
        ]),
      ),
      http.get("/api/jobs/1/source-overrides", () =>
        HttpResponse.json([
          {
            field: "remote_policy",
            revision: 2,
            value: "remote",
            removed: false,
          },
        ]),
      ),
      http.put(
        "/api/jobs/1/source-overrides/remote_policy",
        async ({ request }) => {
          submitted = await request.json();
          return HttpResponse.json({ revision: 3 });
        },
      ),
    );
    render(<SourceCorrections jobId={1} />, { wrapper: withQueryClient });
    await userEvent.click(
      screen.getByRole("button", { name: "Review source fields" }),
    );
    await userEvent.selectOptions(
      await screen.findByLabelText("Work policy"),
      "",
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Save corrections" }),
    );
    await waitFor(() =>
      expect(submitted).toEqual({
        field: "remote_policy",
        value: null,
        expectedRevision: 2,
      }),
    );
  });
});
