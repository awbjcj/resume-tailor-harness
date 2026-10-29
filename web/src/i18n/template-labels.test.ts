import { describe, expect, it } from "vitest";

import { localizeTemplate } from "./template-labels";

describe("template display labels", () => {
  it("translates built-in labels without changing identifiers or custom names", () => {
    const bundled = {
      id: "classic",
      kind: "bundled" as const,
      title: "Classic",
      description: "Compact single-column resume with clear section hierarchy.",
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
      description: "紧凑的单栏简历，章节层次清晰。",
    });
    expect(localizeTemplate(custom, "zh-CN")).toEqual({ ...custom, description: "上传的模板" });
    expect(localizeTemplate(bundled, "en")).toBe(bundled);
  });
});
