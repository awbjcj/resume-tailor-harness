/// <reference types="node" />

import { transformAsync, type NodePath, type PluginItem } from "@babel/core";
import type { StringLiteral } from "@babel/types";
import { createRequire } from "node:module";
import { describe, expect, it } from "vitest";

const require = createRequire(import.meta.url);
const autoI18nPlugin = require("../../i18n-auto-plugin.cjs") as PluginItem;
const { isLocalizableStringPath } = require("../../i18n-classifier.cjs") as {
  isLocalizableStringPath: (path: NodePath<StringLiteral>) => boolean;
};

describe("automatic i18n build transform", () => {
  it("uses the selected language for implicit and fixed English locale formatting", async () => {
    const result = await transformAsync(
      `
        const number = (1234).toLocaleString("en-US");
        const date = new Date().toLocaleDateString();
        const currency = new Intl.NumberFormat(undefined, { style: "currency", currency: "USD" });
        const clock = Intl.DateTimeFormat().format(new Date());
      `,
      {
        babelrc: false,
        configFile: false,
        plugins: [autoI18nPlugin],
      },
    );

    expect(result?.code?.match(/resolvedLanguage/g)).toHaveLength(4);
    expect(result?.code).not.toContain('"en-US"');
  });

  it("translates display labels without changing protocol values or translation keys", async () => {
    const result = await transformAsync(
      `
        const STATUSES = ["ready", "submitted"];
        const TARGET_STAGE_VALUES = ["tailored", "rendered", "approved", "shortlisted"];
        const JOURNEY_COPY = ["journey.stages.profile.label"];
        const options = [{ value: "ready", label: "Ready" }];
      `,
      {
        babelrc: false,
        configFile: false,
        plugins: [autoI18nPlugin],
      },
    );

    expect(result?.code).toContain('"ready"');
    expect(result?.code).toContain('"submitted"');
    expect(result?.code).toContain(
      'TARGET_STAGE_VALUES = ["tailored", "rendered", "approved", "shortlisted"]',
    );
    expect(result?.code).toContain('"journey.stages.profile.label"');
    expect(result?.code?.match(/\.t\("auto\./g)).toHaveLength(1);
  });

  it("keeps Tailwind class lists raw while translating prose that uses the word block", async () => {
    const result = await transformAsync(
      `
        const className = "block text-sm";
        const options = [{
          value: "blocked",
          label: "A gated reviewer blocks the round before scoring. Its weight and score bands are disabled.",
        }];
      `,
      {
        babelrc: false,
        configFile: false,
        plugins: [autoI18nPlugin],
      },
    );

    expect(result?.code).toContain('"block text-sm"');
    expect(result?.code?.match(/\.t\("auto\./g)).toHaveLength(1);
  });

  it("does not classify canonical stage values as display copy", async () => {
    const localized: string[] = [];
    await transformAsync(
      `const TARGET_STAGE_VALUES = ["tailored", "rendered", "approved", "shortlisted"];`,
      {
        babelrc: false,
        configFile: false,
        plugins: [{
          visitor: {
            StringLiteral(path: NodePath<StringLiteral>) {
              if (isLocalizableStringPath(path)) localized.push(path.node.value);
            },
          },
        } as unknown as PluginItem],
      },
    );

    expect(localized).toEqual([]);
  });
});
