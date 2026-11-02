import { http, HttpResponse } from "msw";
import { beforeEach, expect, it, vi } from "vitest";

import { server } from "@/test/server";
import { openRunResult } from "./result-navigation";

const notifications = vi.hoisted(() => ({ info: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast: notifications }));
beforeEach(() => vi.clearAllMocks());

it("resolves the current result only on user navigation and never replays the run", async () => {
  const navigate = vi.fn();
  let reads = 0;
  server.use(http.get("/api/run-completions/by-run/finished", () => {
    reads++;
    return HttpResponse.json({ resultHref: "/pipeline?job=9&tab=tracking", resultAvailable: true });
  }));
  expect(reads).toBe(0);
  await openRunResult("finished", navigate);
  expect(reads).toBe(1);
  expect(navigate).toHaveBeenCalledWith("/pipeline?job=9&tab=tracking");
  expect(notifications.info).not.toHaveBeenCalled();
});

it("explains the safe fallback when the original result is gone", async () => {
  const navigate = vi.fn();
  server.use(http.get("/api/run-completions/by-run/deleted", () => HttpResponse.json({ resultHref: "/profile", resultAvailable: false })));
  await openRunResult("deleted", navigate);
  expect(notifications.info).toHaveBeenCalledWith("The original result is unavailable. Opening the current workspace.");
  expect(navigate).toHaveBeenCalledWith("/profile");
});

it("keeps the user in place after lookup failure", async () => {
  const navigate = vi.fn();
  server.use(http.get("/api/run-completions/by-run/missing", () => HttpResponse.json({ error: { code: "NOT_FOUND", message: "Missing" } }, { status: 404 })));
  await openRunResult("missing", navigate);
  expect(navigate).not.toHaveBeenCalled();
  expect(notifications.error).toHaveBeenCalledWith("Could not open this result. Try again from operation history.");
});
