import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import { server } from "@/test/server";
import { withQueryClient } from "@/test/utils";
import { SearchConfigForm, type SearchDoc } from "./SearchConfigForm";

const EMPTY: SearchDoc = {
  keywords: [], titles: [], locations: [], remotePolicy: [],
  minSalary: null, yoeMin: null, yoeMax: null, sponsorshipRequired: false,
  roleAnchors: [], excludeTerms: [], targetRole: null,
  distance: null, maxDaysOld: null, experienceLevels: [], employmentTypes: [],
};

function Harness() {
  const [value, setValue] = useState(EMPTY);
  return (
    <>
      <SearchConfigForm value={value} onChange={setValue} />
      <output data-testid="keywords">{value.keywords?.join(",")}</output>
      <output data-testid="remote-policy">{value.remotePolicy?.join(",") ?? ""}</output>
      <output data-testid="locations">{value.locations?.join("|")}</output>
    </>
  );
}

function renderHarness() {
  return render(<Harness />, { wrapper: withQueryClient });
}

describe("SearchConfigForm", () => {
  it("adds and removes keywords and toggles multiple remote policies", async () => {
    const user = userEvent.setup();
    renderHarness();
    await user.type(screen.getByLabelText("Keywords"), "python{Enter}");
    expect(screen.getByTestId("keywords")).toHaveTextContent("python");
    await user.click(screen.getByRole("button", { name: "Remove python" }));
    expect(screen.getByTestId("keywords")).toBeEmptyDOMElement();
    await user.click(screen.getByRole("button", { name: "Remote" }));
    expect(screen.getByTestId("remote-policy")).toHaveTextContent("remote");
    await user.click(screen.getByRole("button", { name: "Hybrid" }));
    expect(screen.getByTestId("remote-policy")).toHaveTextContent("remote,hybrid");
    await user.click(screen.getByRole("button", { name: "Remote" }));
    expect(screen.getByTestId("remote-policy")).toHaveTextContent("hybrid");
  });

  it("normalizes a newly added location once the server responds", async () => {
    server.use(
      http.post("/api/config/search/normalize-locations", async ({ request }) => {
        const { raw } = (await request.json()) as { raw: string[] };
        return HttpResponse.json({ normalized: raw.map(() => "Austin, TX") });
      }),
    );
    const user = userEvent.setup();
    renderHarness();
    await user.type(screen.getByLabelText("Locations"), "austin tx{Enter}");
    await waitFor(() =>
      expect(screen.getByTestId("locations")).toHaveTextContent("Austin, TX"),
    );
  });

  it("preserves commas in a location and keeps edits made during normalization", async () => {
    let finish = () => {};
    const pending = new Promise<void>((resolve) => { finish = resolve; });
    server.use(
      http.post("/api/config/search/normalize-locations", async ({ request }) => {
        const { raw } = (await request.json()) as { raw: string[] };
        await pending;
        return HttpResponse.json({ normalized: raw.map((location) => location === "austin, tx" ? "Austin, TX" : location) });
      }),
    );
    const user = userEvent.setup();
    renderHarness();
    await user.type(screen.getByLabelText("Locations"), "austin, tx{Enter}");
    expect(screen.getByTestId("locations").textContent).toBe("austin, tx");
    await user.type(screen.getByLabelText("Keywords"), "platform{Enter}");
    finish();
    await waitFor(() => expect(screen.getByTestId("locations").textContent).toBe("Austin, TX"));
    expect(screen.getByTestId("keywords").textContent).toBe("platform");
  });

  it("leaves the raw location text alone when normalization fails", async () => {
    server.use(
      http.post("/api/config/search/normalize-locations", () => HttpResponse.error()),
    );
    const user = userEvent.setup();
    renderHarness();
    await user.type(screen.getByLabelText("Locations"), "somewhere odd{Enter}");
    await waitFor(() =>
      expect(screen.getByTestId("locations")).toHaveTextContent("somewhere odd"),
    );
  });
});
