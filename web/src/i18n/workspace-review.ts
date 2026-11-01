import { useTranslation } from "react-i18next";

// Keep feature-only copy with the deferred review UI, outside the startup catalog.
const copy = {
  en: {
    title: "Workspace changes",
    help: "Review the exact changes below. Nothing is applied until you approve.",
    unconfirmed: "Outcome unconfirmed — do not retry",
    loading: "Loading proposed changes…",
    noMore: "No more proposed changes.",
    pages: "Proposed changes pages",
    emptyText: "Empty text",
    emptyList: "Empty list",
    noFields: "No fields",
    newTab: "(opens in a new tab)",
    saving: "Saving selected changes…",
    discarding: "Discarding selected changes…",
    select: "Select a change to approve or discard.",
    selection: (selected: number, total: number) => `Selected ${selected} of ${total} changes`,
  },
  "zh-CN": {
    title: "工作区更改",
    help: "请核对以下具体变更。批准后才会执行。",
    unconfirmed: "执行结果尚未确认，请勿重试",
    loading: "正在加载待审核更改…",
    noMore: "没有更多待审核更改。",
    pages: "待审核更改分页",
    emptyText: "空文本",
    emptyList: "空列表",
    noFields: "无字段",
    newTab: "（在新标签页中打开）",
    saving: "正在保存所选更改…",
    discarding: "正在舍弃所选更改…",
    select: "请选择要批准或舍弃的更改。",
    selection: (selected: number, total: number) => `已选择 ${selected} 项更改，共 ${total} 项`,
  },
};

export function useWorkspaceReviewCopy() {
  const { i18n } = useTranslation();
  return copy[i18n.resolvedLanguage === "zh-CN" ? "zh-CN" : "en"];
}
