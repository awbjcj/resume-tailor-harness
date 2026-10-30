import { describe, expect, it } from "vitest";

import { isPublicHttpUrl } from "./PublicUrlField";

describe("public URL syntax", () => {
  it.each(["https:example.com", "https:/example.com", "https://user:pass@example.com", "https://@example.com", "https://example.com\\jobs", "https://", "ftp://example.com/job"])("rejects server-incompatible %s", (url) => {
    expect(isPublicHttpUrl(url)).toBe(false);
  });
  it.each(["https://example.com/jobs/123?source=email", " http://example.com/job "])("accepts complete %s", (url) => {
    expect(isPublicHttpUrl(url)).toBe(true);
  });
});
