import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { expect, it, vi } from "vitest";

import { server } from "@/test/server";
import { withQueryClient } from "@/test/utils";
import { SearchSettingsPage } from "./SearchSettingsPage";

it("saves the normalized locations after the slowest response completes", async () => {
  let finishAustin = () => {};
  const pendingAustin = new Promise<void>((resolve) => { finishAustin = resolve; });
  const saved = vi.fn();
  server.use(
    http.get("/api/config/search", () => HttpResponse.json({ locations: [], keywords: [] })),
    http.post("/api/config/search/normalize-locations", async ({ request }) => {
      const { raw } = (await request.json()) as { raw: string[] };
      if (raw[0] === "austin tx") await pendingAustin;
      return HttpResponse.json({ normalized: raw.map((value) => value === "austin tx" ? "Austin, TX" : "Seattle, WA") });
    }),
    http.put("/api/config/search", async ({ request }) => {
      const body = await request.json();
      saved(body);
      return HttpResponse.json(body);
    }),
  );
  const user = userEvent.setup();
  render(<SearchSettingsPage />, { wrapper: withQueryClient });
  const location = await screen.findByLabelText("Locations");
  await user.type(location, "austin tx{Enter}seattle wa{Enter}");
  await screen.findByRole("button", { name: "Remove Seattle, WA" });
  const save = screen.getByRole("button", { name: "Save changes" });
  try {
    expect(save).toBeDisabled();
    expect(saved).not.toHaveBeenCalled();
  } finally {
    finishAustin();
  }
  await waitFor(() => expect(save).toBeEnabled());
  await user.click(save);
  await waitFor(() => expect(saved).toHaveBeenCalledWith(
    expect.objectContaining({ locations: ["Austin, TX", "Seattle, WA"] }),
  ));
});
