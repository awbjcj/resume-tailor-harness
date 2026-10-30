import { describe, expect, it } from "vitest";

import { localizeTemplate } from "./template-labels";

describe("template display labels", () => {
  it("translates built-in labels without changing identifiers or custom names", () => {
    const bundled = {
      id: "classic",
      kind: "bundled" as const,
      title: "Classic",
      description: "Traditional serif layout for general applications and conservative industries.",
    };
    const custom = {
      id: "custom:Classic",
      kind: "custom" as const,
      title: "Classic",
      description: "Uploaded template",
    };

    expect(localizeTemplate(bundled, "zh-CN")).toEqual({
      ...bundled,
      title: "经典",
      description: "传统衬线字体布局，适合一般求职和风格较保守的行业。",
    });
    expect(localizeTemplate(custom, "zh-CN")).toEqual({ ...custom, description: "上传的模板" });
    expect(localizeTemplate(bundled, "en")).toBe(bundled);
  });
});
