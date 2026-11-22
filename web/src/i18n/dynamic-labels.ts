import zhCN from "./dynamic-zh-CN.json";

import { runLabel, runLabelKey, type RunLabelKey } from "@/lib/runs/labels";

type Translate = (key: RunLabelKey) => string;

const PLACEHOLDER = "{{value}}";

function isChinese(language: string | null | undefined): boolean {
  return language?.toLowerCase().startsWith("zh") ?? false;
}

/** Display known API enums without translating values used in requests. */
export function localizeDisplayValue(value: string, language: string | null | undefined): string {
  if (isChinese(language)) {
    const key = value.toLowerCase() as keyof typeof zhCN.displayValues;
    if (zhCN.displayValues[key]) return zhCN.displayValues[key];
  }
  return value.replaceAll("_", " ");
}

const GROUPING_REASONS_ZH: Record<string, string> = {
  "Deferred by taxonomy usage limits; explicitly retry selected skills": "因技能分类用量限制而延后，请手动重试所选技能",
  "no high-confidence existing or coherent new domain": "没有足够把握将其归入现有领域或新建一致的领域",
  "Provisional category placement; a specific domain still needs confirmation": "暂时归入此类别，具体领域仍需确认",
  "canonicalization incomplete; kept as its own canonical": "技能名称归一化尚未完成，暂时保留为独立名称",
  "reconcile left new canonicals unmerged; kept as-is": "部分新技能名称尚未合并，暂时保持原样",
  "invalid or incomplete model output": "模型输出无效或不完整",
  "new-domain proposal did not meet the deterministic coherence gate": "建议的新领域未通过一致性检查",
  "model call failed": "模型调用失败",
};

/** Preserve unrecognized diagnostic details while translating known grouping outcomes. */
export function localizeGroupingStatus(
  status: { state: string; reason: string },
  language: string | null | undefined,
): string {
  if (!isChinese(language)) return `Grouping ${status.state}: ${status.reason}`;
  const state = status.state === "uncertain" ? "待确认" : localizeDisplayValue(status.state, language);
  const reason = GROUPING_REASONS_ZH[status.reason] ?? status.reason;
  return `分组${state}：${reason}`;
}

function translateTemplate(table: Record<string, string>, value: string): string | null {
  if (table[value]) return table[value];

  let bestMatch: { sourceLength: number; translation: string } | null = null;
  for (const [source, translation] of Object.entries(table)) {
    const parts = source.split(PLACEHOLDER);
    if (parts.length === 1) continue;
    const pattern = parts.map((part) => part.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("(.*?)");
    const match = new RegExp(`^${pattern}$`, "s").exec(value);
    if (match) {
      const sourceLength = parts.join("").length;
      if (!bestMatch || sourceLength > bestMatch.sourceLength) {
        let capture = 1;
        bestMatch = {
          sourceLength,
          translation: translation.replaceAll(PLACEHOLDER, () => match[capture++] ?? ""),
        };
      }
    }
  }
  return bestMatch?.translation ?? null;
}

export function localizeRunKind(kind: string, language: string | null | undefined, t: Translate): string {
  const key = runLabelKey(kind);
  if (key) return t(key);
  return isChinese(language) ? zhCN.fallbacks.unknownRun : runLabel(kind);
}

export function localizeRunPhase(phase: string, language: string | null | undefined): string {
  if (!phase || !isChinese(language)) return phase;
  return translateTemplate(zhCN.runPhases, phase) ?? zhCN.fallbacks.working;
}

const EN_RUN_ERRORS: Record<string, string> = {
  "GmailApiError: A Gmail sync is already running for this workspace.": "A Gmail sync is already running for this workspace.",
  "GmailApiError: Gmail did not return a mailbox identity and sync cursor.": "Gmail did not return a mailbox identity and sync cursor.",
  "GmailApiError: Gmail repeated a page cursor. Saved progress is retained; try again later.": "Gmail repeated a page cursor. Saved progress is retained; try again later.",
  "GmailNotConnected: Connect Gmail again in Settings to resume syncing.": "Reconnect Gmail in Settings to resume syncing.",
  "GmailScopeMissing: Reconnect Gmail in Settings and approve Gmail read access.": "Reconnect Gmail in Settings and grant Gmail read access.",
  "GmailApiError: Gmail could not refresh its connection. Try syncing again later.": "Gmail could not refresh its connection. Try syncing again later.",
  "GmailApiError: Google is temporarily unreachable. Try syncing again later.": "Google is temporarily unreachable. Try syncing again later.",
  "GmailApiError: Gmail could not complete the scan after retries. Try syncing again later.": "Gmail could not complete the scan after retries. Try syncing again later.",
  "GmailNotConnected: Gmail is not connected for this workspace": "Gmail is not connected for this workspace.",
  "GmailNotConnected: Connect Gmail in Settings to save drafts": "Connect Gmail in Settings to save drafts.",
};

export function localizeRunError(error: string | null | undefined, language: string | null | undefined): string | null {
  if (!error) return null;
  if (!isChinese(language)) return EN_RUN_ERRORS[error] ?? error;
  return zhCN.runErrors[error as keyof typeof zhCN.runErrors]
    ?? (error.startsWith("GmailNotConnected:")
      ? zhCN.runErrors["GmailNotConnected: Gmail is not connected for this workspace"]
      : zhCN.fallbacks.operationFailed);
}

/** Logs mix progress and errors; retain diagnostic text when no translation exists. */
export function localizeRunLogMessage(message: string, language: string | null | undefined): string {
  if (!message || !isChinese(language)) return message;
  return translateTemplate(zhCN.runPhases, message)
    ?? translateTemplate(zhCN.runErrors, message)
    ?? message;
}

export function localizeSourceMode(mode: string, language: string | null | undefined): string {
  if (!isChinese(language)) return {
    auto: "Auto-detect", literal: "Resume / text", synthesis: "Verified synthesis", project: "Project dossier",
  }[mode] ?? mode;
  if (mode === "auto") return "自动识别";
  return zhCN.sourceModes[mode as keyof typeof zhCN.sourceModes] ?? zhCN.fallbacks.unknownMode;
}

export function localizeSourceFragmentStatus(status: string, language: string | null | undefined): string {
  if (!isChinese(language)) return {
    cached: "Ready", extracted: "Extracted", missing: "Needs build", stale: "Needs rebuild", "source-changed": "Needs rebuild",
  }[status] ?? status;
  return zhCN.sourceFragmentStatuses[status as keyof typeof zhCN.sourceFragmentStatuses]
    ?? zhCN.fallbacks.unknownStatus;
}

const EN_RUN_STATUSES: Record<string, string> = {
  queued: "queued",
  cancelling: "cancelling",
  succeeded: "done",
  failed: "failed",
  cancelled: "cancelled",
};

export function localizeRunStatus(status: string, language: string | null | undefined): string {
  if (!isChinese(language)) return EN_RUN_STATUSES[status] ?? status;
  return zhCN.runStatuses[status as keyof typeof zhCN.runStatuses] ?? zhCN.fallbacks.unknownStatus;
}

const ETA_UNIT_LABELS: Record<string, string> = {
  h: "小时",
  m: "分",
  s: "秒",
};

/**
 * Formats the compact ETA emitted by the run API without exposing its English
 * units in Chinese mode. The API currently emits forms such as `10m 14s`.
 */
export function localizeRunEta(etaText: string | null | undefined, language: string | null | undefined): string | null {
  if (!etaText) return null;
  if (!isChinese(language)) return `~${etaText} left`;

  const parts = Array.from(etaText.matchAll(/(\d+)\s*([hms])/gi));
  const remainder = etaText.replace(/(\d+)\s*([hms])/gi, "").replace(/[~\s]/g, "");
  if (parts.length === 0 || remainder) return zhCN.fallbacks.etaUnknown;

  const duration = parts
    .map(([, amount, unit]) => `${amount} ${ETA_UNIT_LABELS[unit.toLowerCase()]}`)
    .join(" ");
  return `约剩 ${duration}`;
}
