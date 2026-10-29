/// <reference types="node" />

import { transformAsync, type NodePath, type PluginItem } from "@babel/core";
import type { StringLiteral } from "@babel/types";
import { createRequire } from "node:module";
import { describe, expect, it } from "vitest";
import i18n, { changeLanguage } from "./index";

const require = createRequire(import.meta.url);
const autoI18nPlugin = require("../../i18n-auto-plugin.cjs") as PluginItem;
const { isLocalizableStringPath } = require("../../i18n-classifier.cjs") as {
  isLocalizableStringPath: (path: NodePath<StringLiteral>) => boolean;
};

describe("automatic i18n build transform", () => {
  it("reads module-level labels in the current language without translating option values", async () => {
    const result = await transformAsync(`
      const LABELS = { ready: "Ready" };
      const options = [{ value: "ready", label: "Ready" }];
    `, { babelrc: false, configFile: false, plugins: [autoI18nPlugin] });
    const code = result?.code ?? "";
    const importLine = /import (\w+) from "@\/i18n";/;
    const identifier = code.match(importLine)?.[1];
    expect(identifier).toBeTruthy();
    const evaluate = new Function(identifier!, `${code.replace(importLine, "")}\nreturn { LABELS, options };`);
    const display = evaluate(i18n) as { LABELS: { ready: string }; options: { value: string; label: string }[] };

    await changeLanguage("en");
    expect(display.LABELS.ready).toBe("Ready");
    await changeLanguage("zh-CN");
    expect(display.LABELS.ready).toBe("就绪");
    expect(display.options[0]).toEqual({ value: "ready", label: "就绪" });
    await changeLanguage("en");
    expect(display.options[0].label).toBe("Ready");
  });

  it("translates display branches inside templates and rendered map callbacks", async () => {
    const result = await transformAsync(`
      function View({ row, rows }) {
        return <div title={\`\${row.status === "ready" ? "Active" : "Complete"}\`}>
          {rows.map((item) => \`Added \${item.title}\`)}
        </div>;
      }
    `, { babelrc: false, configFile: false, parserOpts: { plugins: ["jsx"] }, plugins: [autoI18nPlugin] });

    expect(result?.code).toContain('row.status === "ready"');
    expect(result?.code).not.toContain('"Active"');
    expect(result?.code).not.toContain('"Complete"');
    expect(result?.code).not.toContain("`Added");
    expect(result?.code?.match(/\.t\("auto\./g)).toHaveLength(4);
  });

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
          label: "If a gated reviewer fails, the round fails regardless of its score. Gate reviewers do not contribute a score, so their weight and score bands are disabled.",
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

  it("preserves status mapper return values while translating explicit status labels", async () => {
    const localized: string[] = [];
    const result = await transformAsync(
      `
        function stateToStatus(state: string): RunRecord["status"] {
          switch (state) {
            case "done": return "succeeded";
            case "error": return "failed";
            default: return "running";
          }
        }
        const mapStatus = (state: string) => state === "done" ? "succeeded" : "running";
        const status = "running";
        const TERMINAL_STATUSES: readonly RunRecord["status"][] = ["succeeded", "failed", "cancelled"];
        const ACTIVE_RUN_STATUSES: RunRecord["status"][] = ["queued", "running", "cancelling"];
        function runStatusLabel() { return "Completed"; }
      `,
      {
        babelrc: false,
        configFile: false,
        parserOpts: { plugins: ["typescript"] },
        plugins: [{
          visitor: {
            StringLiteral(path: NodePath<StringLiteral>) {
              if (isLocalizableStringPath(path)) localized.push(path.node.value);
            },
          },
        } as unknown as PluginItem, autoI18nPlugin],
      },
    );

    expect(result?.code).toContain('return "succeeded"');
    expect(result?.code).toContain('return "failed"');
    expect(result?.code).toContain('return "running"');
    expect(result?.code).toContain('state === "done" ? "succeeded" : "running"');
    expect(result?.code).toContain('const status = "running"');
    expect(result?.code).toContain('["succeeded", "failed", "cancelled"]');
    expect(result?.code).toContain('["queued", "running", "cancelling"]');
    expect(localized).toEqual(["Completed"]);
    expect(result?.code?.match(/\.t\("auto\./g)).toHaveLength(1);
  });
});
