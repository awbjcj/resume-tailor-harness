import i18n from "i18next";

export const applicationListEn = {
  sortBy: "Sort by",
  status: "Status",
  allStatuses: "All statuses",
  sortOptions: {
    newest: "Newest activity",
    companyAscending: "Company A–Z",
    companyDescending: "Company Z–A",
    status: "Group by status",
  },
  showing: "Matching applications: {{shown}} of {{total}}",
  loadError: "Could not load applications",
  noMatches: "No applications match these filters.",
  clearFilters: "Clear filters",
  pages: "Application pages",
  pageNumber: "Page {{page}} of {{total}}",
  previousPage: "Previous application page",
  nextPage: "Next application page",
  comparison: {
    column: "Compare",
    selectRole: "Select {{company}} {{role}} for comparison",
    terminalRole: "{{company}} {{role}} is closed and cannot be compared",
    unknownRole: "role",
    kicker: "Stored evidence only",
    title: "Role comparison",
    description:
      "Missing information is marked. This table does not call a model or guess answers.",
    headers: {
      role: "Role",
      fit: "Fit",
      stage: "Stage",
      companyEvidence: "Company evidence",
      h1bEvidence: "H-1B evidence",
      latestOffer: "Latest offer",
    },
    notResearched: "Not researched",
    noClaims: "no claims",
    stale: "stale",
    current: "current",
    unknownDepth: "unknown depth",
    evidenceSummary:
      "{{depth}} · {{count}} sources · {{verification}} · {{freshness}}",
    depth: { quick: "quick", standard: "standard", deep: "deep" },
    verification: {
      inferred: "inferred",
      single_source: "single source",
      corroborated: "corroborated",
    },
    sponsorship: {
      matched: "Historical filing match",
      noMatch: "No historical match",
      unavailable: "Research unavailable",
      notChecked: "Not checked",
    },
    notScored: "Not scored",
    noStructuredOffer: "No structured offer",
  },
};

const zh: typeof applicationListEn = {
  sortBy: "排序方式",
  status: "状态",
  allStatuses: "全部状态",
  sortOptions: {
    newest: "最新动态",
    companyAscending: "公司名称 A–Z",
    companyDescending: "公司名称 Z–A",
    status: "按申请状态分组",
  },
  showing: "符合条件的申请：{{shown}} 条，共 {{total}} 条",
  loadError: "无法加载申请记录",
  noMatches: "没有符合筛选条件的申请记录。",
  clearFilters: "清除筛选",
  pages: "申请记录分页",
  pageNumber: "第 {{page}} 页，共 {{total}} 页",
  previousPage: "上一页申请记录",
  nextPage: "下一页申请记录",
  comparison: {
    column: "对比",
    selectRole: "选择 {{company}} 的 {{role}} 进行对比",
    terminalRole: "{{company}} 的 {{role}} 已结束，无法对比",
    unknownRole: "职位",
    kicker: "仅使用已保存的证据",
    title: "职位对比",
    description: "缺失的信息会明确标出，这张表不会调用模型推测答案。",
    headers: {
      role: "职位",
      fit: "匹配度",
      stage: "阶段",
      companyEvidence: "公司调研依据",
      h1bEvidence: "H-1B 证据",
      latestOffer: "最新录用通知",
    },
    notResearched: "尚未调研",
    noClaims: "无结论",
    stale: "已过时",
    current: "当前有效",
    unknownDepth: "深度未知",
    evidenceSummary:
      "{{depth}} · {{count}} 个来源 · {{verification}} · {{freshness}}",
    depth: { quick: "快速", standard: "标准", deep: "深度" },
    verification: {
      inferred: "推断",
      single_source: "单一来源",
      corroborated: "多来源印证",
    },
    sponsorship: {
      matched: "找到历史申报记录",
      noMatch: "未找到历史申报记录",
      unavailable: "调研暂不可用",
      notChecked: "尚未检查",
    },
    notScored: "尚未评分",
    noStructuredOffer: "尚未记录录用通知的具体信息",
  },
};

function register() {
  i18n.addResourceBundle("en", "translation", { applications: applicationListEn }, true, true);
  i18n.addResourceBundle("zh-CN", "translation", { applications: zh }, true, true);
}

if (i18n.isInitialized) register();
else i18n.on("initialized", register);
