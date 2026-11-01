import { describe, expect, it } from "vitest";

import zhCN from "./dynamic-zh-CN.json";
import {
  localizeRunError,
  localizeRunEta,
  localizeRunLogMessage,
  localizeRunPhase,
  localizeDisplayValue,
  localizeSourceFragmentStatus,
  localizeSourceMode,
} from "./dynamic-labels";

describe("dynamic Chinese labels", () => {
  it("translates API display values while preserving English and unknown diagnostic values", () => {
    for (const [value, translated] of Object.entries(zhCN.displayValues)) {
      expect(localizeDisplayValue(value, "zh-CN")).toBe(translated);
      expect(localizeDisplayValue(value, "en")).toBe(value.replaceAll("_", " "));
    }
    expect(localizeDisplayValue("OWNERSHIP_NOT_PROVEN", "zh-CN")).toBe("尚未核实招聘页面归属");
    expect(localizeDisplayValue("future_status", "zh-CN")).toBe("future status");
  });
  it("translates every backend progress label covered by the catalog", () => {
    for (const [source, translation] of Object.entries(zhCN.runPhases)) {
      const runtimeSource = source.replaceAll("{{value}}", "示例");
      expect(localizeRunPhase(runtimeSource, "zh-CN")).toBe(
        translation.replaceAll("{{value}}", "示例"),
      );
      expect(localizeRunLogMessage(runtimeSource, "zh-CN")).toBe(
        translation.replaceAll("{{value}}", "示例"),
      );
    }
  });

  it("translates known errors in logs and preserves unmapped diagnostic details", () => {
    for (const [source, translation] of Object.entries(zhCN.runErrors)) {
      expect(localizeRunLogMessage(source, "zh-CN")).toBe(translation);
    }
    for (const message of ["Imported 12 source documents", "Provider timeout after 30s", "已保存 12 份文档", ""]) {
      expect(localizeRunLogMessage(message, "zh-CN")).toBe(message);
      expect(localizeRunLogMessage(message, "en")).toBe(message);
    }
    expect(localizeRunLogMessage("Draft is ready", "en")).toBe("Draft is ready");
  });

  it("preserves distinct processed and cached counts in Gmail progress", () => {
    expect(localizeRunPhase("Processed 50 emails; reused 25 cached results", "zh-CN")).toBe(
      "已处理 50 封邮件；复用了 25 条缓存结果",
    );
  });

  it("distinguishes saved sync continuation from warnings in Chinese", () => {
    expect(localizeRunPhase("Sync complete; more emails remain", "zh-CN")).toBe(
      "本次同步已完成；仍有邮件待处理",
    );
  });

  it("does not leak unrecognized backend phases or errors in Chinese mode", () => {
    expect(localizeRunPhase("Future backend phase", "zh-CN")).toBe("正在处理");
    expect(localizeRunError("Provider unavailable", "zh-CN")).toBe("操作失败。请重试。");
    expect(localizeRunError(
      "GmailNotConnected: Gmail is not connected for this workspace",
      "zh-CN",
    )).toBe("Gmail 尚未连接到此工作区。");
  });

  it("shows readable known Gmail errors in English while retaining unknown errors", () => {
    expect(localizeRunError(
      "GmailScopeMissing: Reconnect Gmail in Settings and approve Gmail read access.",
      "en",
    )).toBe("Reconnect Gmail in Settings and grant Gmail read access.");
    expect(localizeRunError("Provider timeout after 30s", "en")).toBe("Provider timeout after 30s");
    expect(localizeRunLogMessage(
      "GmailScopeMissing: Reconnect Gmail in Settings and approve Gmail read access.",
      "en",
    )).toBe("GmailScopeMissing: Reconnect Gmail in Settings and approve Gmail read access.");
  });

  it("uses Chinese display labels without changing source protocol values", () => {
    expect(localizeSourceMode("literal", "zh-CN")).toBe("简历／文本");
    expect(localizeSourceMode("synthesis", "zh-CN")).toBe("提炼并核验");
    expect(localizeSourceMode("project", "zh-CN")).toBe("项目档案");
    expect(localizeSourceFragmentStatus("cached", "zh-CN")).toBe("已就绪");
    expect(localizeSourceFragmentStatus("source-changed", "zh-CN")).toBe("待重新构建");
    expect(localizeSourceFragmentStatus("missing", "zh-CN")).toBe("待构建");
    expect(localizeSourceFragmentStatus("missing", "en")).toBe("Needs build");
    expect(localizeSourceFragmentStatus("cached", "en")).toBe("Ready");
    expect(localizeSourceMode("synthesis", "en")).toBe("Verified synthesis");
  });

  it("formats API ETA values in Chinese without leaking English units", () => {
    expect(localizeRunEta("10m 14s", "zh-CN")).toBe("约剩 10 分 14 秒");
    expect(localizeRunEta("1h 2m 3s", "zh-CN")).toBe("约剩 1 小时 2 分 3 秒");
    expect(localizeRunEta("soon", "zh-CN")).toBe("无法预计完成时间");
    expect(localizeRunEta("2m", "en")).toBe("~2m left");
  });
});
