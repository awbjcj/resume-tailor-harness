import i18n from "i18next";
export const roadmapEn = {
  backToList: "Back to roadmaps",
  filterStatus: "Filter by progress", resetFilters: "Reset filters",
  resource_doc: "Documentation", resource_course: "Course", resource_tutorial: "Tutorial",
  suggestionStatus: { none: "Not generated", ready: "Ready", stale: "Needs review", queued: "Queued", researching: "Researching", failed: "Failed", cancelled: "Cancelled", not_found: "Unavailable" },
  viewDomain: "View domain roadmap", domainDescription: "Learning roadmap for this domain and its related skills.",
  title: "Learning roadmaps", description: "View saved advice for skills and domains, update your progress, and revisit completed plans.",
  library: "Saved roadmaps", searchPlaceholder: "Skill, domain, or keyword", viewRoadmap: "View roadmap",
  back: "Explore skill gaps", search: "Search roadmaps", status: "Progress", all: "All progress", active: "Not archived",
  planned: "Planned", in_progress: "In progress", completed: "Completed", archived: "Archived",
  empty: "No roadmaps yet", emptyBody: "Generate advice for a skill or domain in Match Gap to save your first roadmap.",
  noMatches: "No roadmaps match these filters.", archivedOnly: "All your roadmaps are archived", viewArchived: "View archived roadmaps",
  supersededLabel: "Superseded", unavailableLabel: "Unavailable", noSavedAdvice: "Saved advice is unavailable.",
  unavailable: "This skill or domain is no longer in your skill map. You can still view the saved roadmap, but you can't regenerate it.",
  superseded: "Another roadmap now represents this skill. You can still view this plan and update its progress, but it can't be regenerated.",
  openCurrent: "Open current roadmap",
  saving: "Saving progress…", saved: "Progress saved", saveError: "Could not save progress. Try again.", loading: "Loading roadmaps", error: "Could not load roadmaps.",
  retry: "Retry", skill: "Skill", domain: "Domain", stale: "Needs review", updated: "Generated {{date}}", count_one: "{{count}} roadmap", count_other: "{{count}} roadmaps",
  resultRange: "{{first}}–{{last}} of {{count}} roadmaps", resultLast: "{{last}} of {{count}} roadmaps",
  pagination: "Roadmap pages", pageOf: "Page {{page}} of {{total}}",
  previousPage: "Previous roadmap page", nextPage: "Next roadmap page",
  stars_one: "{{count, number}} star", stars_other: "{{count, number}} stars",
  missing: "This roadmap is no longer available. Choose another plan.",
};
const zh: typeof roadmapEn = {
  backToList: "返回学习路线列表",
  filterStatus: "按学习进度筛选", resetFilters: "重置筛选",
  resource_doc: "文档", resource_course: "课程", resource_tutorial: "教程",
  suggestionStatus: { none: "未生成", ready: "已就绪", stale: "待复查", queued: "已排队", researching: "调研中", failed: "失败", cancelled: "已取消", not_found: "暂不可用" },
  viewDomain: "查看领域学习路线", domainDescription: "此领域及其相关技能的学习路线。",
  title: "学习路线", description: "查看已保存的技能和领域学习建议，更新进度，并回顾已完成的计划。",
  library: "已保存的学习路线", searchPlaceholder: "技能、领域或关键词", viewRoadmap: "查看学习路线",
  back: "探索技能差距", search: "搜索学习路线", status: "学习进度", all: "所有进度", active: "未归档",
  planned: "待学习", in_progress: "学习中", completed: "已完成", archived: "已归档",
  empty: "暂无学习路线", emptyBody: "在“匹配差距”页面为技能或领域生成建议，即可保存第一条学习路线。",
  noMatches: "没有符合筛选条件的学习路线。", archivedOnly: "所有学习路线均已归档", viewArchived: "查看已归档的学习路线",
  supersededLabel: "已被替代", unavailableLabel: "已不可用", noSavedAdvice: "无法查看已保存的学习建议。",
  unavailable: "此技能或领域已不在技能图谱中。你仍可查看保存的学习路线，但无法重新生成。",
  superseded: "此技能现在对应另一条学习路线。你仍可查看此计划并更新进度，但无法重新生成。",
  openCurrent: "打开当前学习路线",
  saving: "正在保存进度…", saved: "进度已保存", saveError: "无法保存进度，请重试。", loading: "正在加载学习路线", error: "无法加载学习路线。",
  retry: "重试", skill: "技能", domain: "领域", stale: "待复查", updated: "生成于 {{date}}", count_one: "{{count}} 条学习路线", count_other: "{{count}} 条学习路线",
  resultRange: "第 {{first}}–{{last}} 条，共 {{count}} 条学习路线", resultLast: "第 {{last}} 条，共 {{count}} 条学习路线",
  pagination: "学习路线分页", pageOf: "第 {{page}} 页，共 {{total}} 页",
  previousPage: "上一页学习路线", nextPage: "下一页学习路线",
  stars_one: "{{count, number}} 颗星", stars_other: "{{count, number}} 颗星",
  missing: "此学习路线已不可用，请选择其他计划。",
};
function register() {
  i18n.addResourceBundle("en", "translation", { roadmaps: roadmapEn }, true, true);
  i18n.addResourceBundle("zh-CN", "translation", { roadmaps: zh }, true, true);
}
if (i18n.isInitialized) register(); else i18n.on("initialized", register);
