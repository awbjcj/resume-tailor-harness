import { describe, expect, it } from "vitest";

import { formatDateInTimeZone, formatTimeInTimeZone } from "./date-time";

describe("date-time", () => {
  it("renders a UTC instant in the requested current-user timezone", () => {
    const instant = "2026-03-09T19:00:00Z";
    const options = { hour: "2-digit", minute: "2-digit", hourCycle: "h23" } as const;

    expect(formatTimeInTimeZone(instant, "America/New_York", "en-US", options)).toBe("15:00");
    expect(formatTimeInTimeZone(instant, "America/Los_Angeles", "en-US", options)).toBe("12:00");
  });

  it("converts a calendar date when the instant crosses a local-day boundary", () => {
    expect(
      formatDateInTimeZone("2026-03-09T01:00:00Z", "America/Los_Angeles", "en-US", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
      }),
    ).toBe("03/08/2026");
  });
});
