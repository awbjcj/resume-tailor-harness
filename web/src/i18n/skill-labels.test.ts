import { describe, expect, it } from "vitest";
import { localizeSkillContainer, localizeSkillLabel } from "./skill-labels";

describe("skill display labels", () => {
  it("localizes defaults and cleanup reasons while preserving custom names", () => {
    expect(localizeSkillContainer({ label: "Programming Languages" }, "zh-CN").label).toBe("编程语言");
    expect(localizeSkillContainer({ label: "Programming Languages", customized: true }, "zh-CN").label).toBe("Programming Languages");
    expect(localizeSkillContainer({ label: "My tools", customized: true }, "zh-CN").label).toBe("My tools");
    expect(localizeSkillLabel("Travel or relocation requirement", "zh-CN")).toBe("出差或搬迁要求");
  });
});
