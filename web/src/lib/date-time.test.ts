import { describe, expect, it } from "vitest";

import { changeLanguage } from "@/i18n";
import { formatDateInTimeZone, formatDateTimeInTimeZone, formatTimeInTimeZone } from "./date-time";

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

  it("uses the selected language by default while respecting an explicit locale", async () => {
    const instant = "2026-12-01T00:00:00Z";
    const zone = "America/New_York";
    const options = { month: "long", day: "numeric", hour: "numeric", minute: "2-digit" } as const;
    const expected = (locale: string) => new Date(instant).toLocaleString(locale, { ...options, timeZone: zone });

    await changeLanguage("zh-CN");
    expect(formatDateTimeInTimeZone(instant, zone, undefined, options)).toBe(expected("zh-CN"));
    expect(formatDateTimeInTimeZone(instant, zone, "en-US", options)).toBe(expected("en-US"));
    expect(formatDateInTimeZone(instant, zone)).toBe(new Date(instant).toLocaleDateString("zh-CN", { timeZone: zone }));
    expect(formatTimeInTimeZone(instant, zone)).toBe(new Date(instant).toLocaleTimeString("zh-CN", { timeZone: zone }));

    await changeLanguage("en");
    expect(formatDateTimeInTimeZone(instant, zone, undefined, options)).toBe(expected("en"));
  });
});
