import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api, ApiError, createDownloadUrl, getToken, setToken, unwrap, withTokenParam } from "./client";

describe("token storage", () => {
  beforeEach(() => localStorage.clear());
  it("round-trips the bearer token", () => {
    expect(getToken()).toBeNull();
    setToken("abc");
    expect(getToken()).toBe("abc");
  });
  it("adds the stored token to browser-native request URLs", () => {
    expect(withTokenParam("/api/runs/1/events")).toBe("/api/runs/1/events");
    setToken("a b");
    expect(withTokenParam("/api/runs/1/events?x=1#tail")).toBe(
      "/api/runs/1/events?x=1&token=a%20b#tail",
    );
  });
});

describe("unwrap", () => {
  it("returns data when present", async () => {
    const r = await unwrap(Promise.resolve({ data: { ok: 1 }, error: undefined }));
    expect(r).toEqual({ ok: 1 });
  });
  it("throws the error envelope message", async () => {
    const env = { error: { error: { code: "NOT_FOUND", message: "nope" } }, data: undefined };
    await expect(unwrap(Promise.resolve(env))).rejects.toThrow("nope");
  });
  it("preserves safe validation details and the machine code", async () => {
    const error = { code: "VALIDATION_ERROR", message: "Check settings", details: [{ loc: ["body", "imap", "host"], type: "value_error" }] };
    const failure = await unwrap(Promise.resolve({ error: { error } })).catch((caught: unknown) => caught);
    expect(failure).toBeInstanceOf(ApiError);
    expect(failure).toMatchObject(error);
  });
});

describe("download URLs", () => {
  afterEach(() => vi.restoreAllMocks());

  it("mints a short download capability and preserves existing parameters and fragments", async () => {
    const post = vi.spyOn(api, "POST").mockResolvedValue({
      data: { token: "short download", expiresInSeconds: 600 },
      response: new Response(),
    });
    const controller = new AbortController();
    const url = new URL(await createDownloadUrl(
      "/api/resume-versions/7/preview?view=full&token=old#page=2", controller.signal,
    ));
    expect(post).toHaveBeenCalledWith("/api/auth/link-token", {
      body: { purpose: "download" }, signal: controller.signal,
    });
    expect(url.pathname).toBe("/api/resume-versions/7/preview");
    expect(url.searchParams.get("view")).toBe("full");
    expect(url.searchParams.getAll("token")).toEqual(["short download"]);
    expect(url.hash).toBe("#page=2");
  });
});
