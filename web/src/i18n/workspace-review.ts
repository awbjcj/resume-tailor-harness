import { useTranslation } from "react-i18next";
import type { components } from "@/lib/api/schema";

type Operation = components["schemas"]["WorkspaceChange"]["operation"];
const operationsEn: Record<Operation, string> = {
  "job.create": "Add job", "job.update": "Update job", "job.archive": "Archive job",
  "job.restore": "Restore job", "job.delete": "Delete job", "application.update": "Update application",
  "event.create": "Add timeline event", "event.update": "Edit event", "event.delete": "Delete event",
  "note.create": "Add note", "note.update": "Update note", "note.delete": "Remove note",
  "preparation.save": "Save preparation", "profile.change": "Update profile",
  "application_profile.update": "Edit application profile", "question.create": "Save question",
  "question.update": "Update answer", "question.delete": "Delete question",
  "artifact.select": "Select document", "artifact.delete": "Delete document", "search.update": "Update search preferences",
};
const operationsZh: Record<Operation, string> = {
  "job.create": "添加职位", "job.update": "修改职位", "job.archive": "归档职位",
  "job.restore": "恢复职位", "job.delete": "删除职位", "application.update": "修改申请",
  "event.create": "添加时间线事件", "event.update": "修改事件", "event.delete": "删除事件",
  "note.create": "添加笔记", "note.update": "修改笔记", "note.delete": "移除笔记",
  "preparation.save": "保存准备材料", "profile.change": "修改个人资料",
  "application_profile.update": "修改申请资料", "question.create": "保存问题",
  "question.update": "修改答案", "question.delete": "删除问题",
  "artifact.select": "选择文档", "artifact.delete": "删除文档", "search.update": "修改搜索偏好",
};

// Keep feature-only copy with the deferred review UI, outside the startup catalog.
const copy = {
  en: {
    title: "Workspace changes",
    help: "Choose which changes to save. Review the preview before approving.",
    unconfirmed: "Outcome unconfirmed. Check the saved record; do not retry this change.",
    loading: "Loading proposed changes…",
    noMore: "No more proposed changes.",
    pages: "Proposed changes pages",
    newTab: "(opens in a new tab)",
    saving: "Saving selected changes…",
    discarding: "Discarding selected changes…",
    select: "Select a change to approve or discard.",
    selection: (selected: number, total: number) => `Selected ${selected} of ${total} changes`,
    pending: (count: number) => `${count} ${count === 1 ? "change" : "changes"} to review`,
    reviewed: "Review complete", expired: "Preview expired", unconfirmedLabel: "Check the outcome",
    expiredHelp: "This preview has expired. Ask the agent for a new one, or discard it.",
    selectAll: "Select all", clearSelection: "Clear selection",
    approve: "Approve and save", discard: "Discard", saved: "Saved", discarded: "Discarded",
    allReviewed: "All changes have been reviewed.",
    details: "Preview changes", sources: "Sources", result: "Saved result",
    job: (id: number) => `Job #${id}`, record: (id: number) => `Record #${id}`,
    deleteHelp: "This deletion is permanent. Review the item before selecting it.",
    deleteJobHelp: "This permanently deletes the job and its practice conversations.",
    profileRemovalHelp: "This change removes profile content. Check the preview before selecting it.",
    deleteSelectionHelp: "Removals start unselected and need a final confirmation.",
    confirmTitle: "Save changes and remove selected items?",
    confirmHelp: "The removals below and all other selected changes will be saved together.",
    confirmAction: "Save and remove", cancel: "Back to review",
    conflict: "The workspace changed or this preview can no longer be used. Ask the agent for a new preview.",
    reviewFailed: "Couldn't complete this review. Your selection is kept. Try again.",
    loadFailed: "Unable to load proposed changes.", retry: "Retry", previous: "Previous", next: "Next",
    operations: operationsEn,
  },
  "zh-CN": {
    title: "工作区更改",
    help: "选择要保存的更改，核对预览后再批准。",
    unconfirmed: "执行结果尚未确认。请检查已保存的记录，不要重复执行。",
    loading: "正在加载待审核更改…",
    noMore: "没有更多待审核更改。",
    pages: "待审核更改分页",
    newTab: "（在新标签页中打开）",
    saving: "正在保存所选更改…",
    discarding: "正在舍弃所选更改…",
    select: "请选择要批准或舍弃的更改。",
    selection: (selected: number, total: number) => `已选择 ${selected} 项更改，共 ${total} 项`,
    pending: (count: number) => `${count} 项更改待审核`,
    reviewed: "审核完成", expired: "预览已过期", unconfirmedLabel: "需核对执行结果",
    expiredHelp: "此预览已过期。可以请助手生成新预览，或舍弃此预览。",
    selectAll: "全选", clearSelection: "清除选择",
    approve: "批准并保存", discard: "舍弃", saved: "已保存", discarded: "已舍弃",
    allReviewed: "所有更改均已审核。",
    details: "查看更改", sources: "参考来源", result: "保存结果",
    job: (id: number) => `职位 #${id}`, record: (id: number) => `记录 #${id}`,
    deleteHelp: "删除后无法恢复，请核对内容后再勾选。",
    deleteJobHelp: "此操作会永久删除职位及相关的练习对话。",
    profileRemovalHelp: "此更改会移除个人资料中的内容，请核对预览后再勾选。",
    deleteSelectionHelp: "移除操作默认不勾选，执行前还需再次确认。",
    confirmTitle: "保存更改并移除所选内容？",
    confirmHelp: "下列移除操作和其他已勾选的更改会一并保存。",
    confirmAction: "保存并移除", cancel: "返回审核",
    conflict: "工作区已发生变化，或此预览已无法使用。请让助手生成新预览。",
    reviewFailed: "未能完成审核，已保留你的选择。请重试。",
    loadFailed: "无法加载待审核更改。", retry: "重试", previous: "上一页", next: "下一页",
    operations: operationsZh,
  },
};

export function useWorkspaceReviewCopy() {
  const { i18n } = useTranslation();
  return copy[i18n.resolvedLanguage === "zh-CN" ? "zh-CN" : "en"];
}
