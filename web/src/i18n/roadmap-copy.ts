import i18n from "i18next";
export const roadmapEn = {
  backToList: "Back to roadmaps",
  filterStatus: "Filter by progress", resetFilters: "Reset filters",
  resource_doc: "Documentation", resource_course: "Course", resource_tutorial: "Tutorial",
  viewDomain: "View domain roadmap", domainDescription: "Learning roadmap for this domain and its related skills.",
  title: "Learning roadmaps", description: "View saved advice for skills and domains, update your progress, and revisit completed plans.",
  back: "Explore skill gaps", search: "Search roadmaps", status: "Progress", all: "All progress", active: "Not archived",
  planned: "Planned", in_progress: "In progress", completed: "Completed", archived: "Archived",
  empty: "No roadmaps yet", emptyBody: "Generate advice for a skill or domain in Match Gap to start your learning library.",
  noMatches: "No roadmaps match these filters.", choose: "Choose a roadmap to review its advice.",
  unavailable: "This skill or domain is no longer in your skill map. You can still view the saved roadmap, but you can't regenerate it.",
  superseded: "Another roadmap now represents this skill. You can still view this plan and update its progress, but it can't be regenerated.",
  openCurrent: "Open current roadmap",
  saved: "Progress saved", saveError: "Could not save progress. Try again.", loading: "Loading roadmaps", error: "Could not load roadmaps.",
  retry: "Retry", skill: "Skill", domain: "Domain", stale: "Needs review", updated: "Generated {{date}}", count_one: "{{count}} roadmap", count_other: "{{count}} roadmaps",
  missing: "This roadmap is no longer available. Choose another plan.",
};
const zh: typeof roadmapEn = {
  backToList: "返回学习路线列表",
  filterStatus: "按学习进度筛选", resetFilters: "重置筛选",
  resource_doc: "文档", resource_course: "课程", resource_tutorial: "教程",
  viewDomain: "查看领域学习路线", domainDescription: "此领域及其相关技能的学习路线。",
  title: "学习路线", description: "查看已保存的技能和领域学习建议，更新进度，并回顾已完成的计划。",
  back: "探索技能差距", search: "搜索学习路线", status: "学习进度", all: "所有进度", active: "未归档",
  planned: "待学习", in_progress: "学习中", completed: "已完成", archived: "已归档",
  empty: "暂无学习路线", emptyBody: "在“匹配差距”页面为技能或领域生成建议，即可开始建立学习路线库。",
  noMatches: "没有符合筛选条件的学习路线。", choose: "选择一条学习路线，查看具体建议。",
  unavailable: "此技能或领域已不在技能图谱中。你仍可查看保存的学习路线，但无法重新生成。",
  superseded: "此技能现在对应另一条学习路线。你仍可查看此计划并更新进度，但无法重新生成。",
  openCurrent: "打开当前学习路线",
  saved: "进度已保存", saveError: "无法保存进度，请重试。", loading: "正在加载学习路线", error: "无法加载学习路线。",
  retry: "重试", skill: "技能", domain: "领域", stale: "待复查", updated: "生成于 {{date}}", count_one: "{{count}} 条学习路线", count_other: "{{count}} 条学习路线",
  missing: "此学习路线已不可用，请选择其他计划。",
};
function register() {
  i18n.addResourceBundle("en", "translation", { roadmaps: roadmapEn }, true, true);
  i18n.addResourceBundle("zh-CN", "translation", { roadmaps: zh }, true, true);
}
if (i18n.isInitialized) register(); else i18n.on("initialized", register);
