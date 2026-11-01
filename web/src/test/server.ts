import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

export const server = setupServer(
  http.get("/api/workspace-agent/proposals", () => HttpResponse.json({ proposals: [], nextOffset: null })),
  http.put("/api/config/language", async ({ request }) => HttpResponse.json(await request.json())),
);
