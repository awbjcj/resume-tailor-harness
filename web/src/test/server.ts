import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

export const server = setupServer(
  http.put("/api/config/language", async ({ request }) => HttpResponse.json(await request.json())),
);
