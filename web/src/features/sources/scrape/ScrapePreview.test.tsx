import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { server } from "@/test/server";
import { withQueryClient } from "@/test/utils";
import { ScrapePreview } from "./ScrapePreview";

describe("scrape review approval", () => {
  it("requires validation after the user changes a selector", async () => {
    server.use(
      http.get("/api/scrape/drafts/draft", () =>
        HttpResponse.json({
          id: "draft",
          sourceId: "board",
          url: "https://example.com/jobs",
          revision: 0,
          validation: { valid: true },
          plan: {
            cardSelector: "article",
            detailMode: "inline",
            detailSelector: ".jd",
          },
          samples: [
            {
              id: "one",
              sourceId: "board",
              revision: 0,
              jobKey: "one",
              accepted: true,
              facts: {
                sourceUrl: "https://example.com/jobs/1",
                title: "Engineer",
                jdText: "Build systems",
              },
            },
          ],
        }),
      ),
    );
    render(
      <ScrapePreview
        draftId="draft"
        onApproved={vi.fn()}
        onValidate={vi.fn()}
      />,
      { wrapper: withQueryClient },
    );
    const approve = await screen.findByRole("button", {
      name: "Approve and save",
    });
    expect(approve).not.toBeDisabled();
    await userEvent.click(screen.getByText("Change extraction rules"));
    await userEvent.type(screen.getByLabelText("Description selector"), "-new");
    expect(approve).toBeDisabled();
  });
});

it("keeps approval errors visible after saving a new draft revision", async () => {
  const draft = {
    id: "draft",
    sourceId: "board",
    url: "https://example.com/jobs",
    revision: 0,
    validation: { valid: true },
    plan: { cardSelector: "article", detailMode: "inline" },
    samples: [
      {
        id: "one",
        jobKey: "one",
        facts: {
          sourceUrl: "https://example.com/1",
          title: "Engineer",
          jdText: "Build tools",
        },
      },
    ],
  };
  server.use(
    http.get("/api/scrape/drafts/draft", () => HttpResponse.json(draft)),
    http.patch("/api/scrape/drafts/draft", () =>
      HttpResponse.json({ ...draft, revision: 1 }),
    ),
    http.post("/api/scrape/drafts/draft/approve", () =>
      HttpResponse.json(
        {
          error: {
            code: "REVISION_CONFLICT",
            message: "Source changed during approval",
          },
        },
        { status: 409 },
      ),
    ),
  );
  render(
    <ScrapePreview draftId="draft" onApproved={vi.fn()} onValidate={vi.fn()} />,
    { wrapper: withQueryClient },
  );
  await userEvent.click(
    await screen.findByRole("button", { name: "Approve and save" }),
  );
  expect(
    await screen.findByText("Source changed during approval"),
  ).toBeVisible();
});
