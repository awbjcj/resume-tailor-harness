import i18n from "i18next";

export const tagListEn = {
  add: "Add",
  addTo: "Add to {{field}}",
  added: "Added {{values}}.",
  alreadyAdded: "Already added.",
  remove: "Remove {{value}}",
  removed: "Removed {{value}}.",
  noMatches: "No matches. You can still add a value.",
  pending: "Press Enter or use Add to add your entry, or clear the field before saving.",
  suggestions: "Suggestions for {{field}}",
  limit: "You can add up to {{count}} values. Remove some or enter fewer at a time.",
  repositories: {
    preferences: "Import preferences",
    search: "Search repositories",
    name: "Repository name",
    loading: "Loading repositories…",
    unavailable: "Repositories could not be loaded. You can still add a name.",
    include: "Always include repositories",
    includeHelp: "These repositories bypass ranking.",
    exclude: "Exclude repositories",
    excludeHelp: "These repositories are skipped during import.",
    limit: "Repository limit",
    limitHelp: "Maximum ranked repositories to import, from 1 to 100.",
    invalidLimit: "Enter a whole number from 1 to 100 to save.",
  },
  offers: {
    heading: "Offers for comparison",
    label: "Offers",
    search: "Company, role, or ID",
    help: "Add up to 10 offers.",
    loading: "Loading offers…",
    unavailable: "Offers could not be loaded. You can still enter an application ID.",
    empty: "No offers found. You can still enter an application ID.",
    invalid: "Choose an offer or enter the ID of an application with an offer.",
  },
  search: {
    keywords: "Keywords",
    keywordExample: "e.g. distributed systems",
    titles: "Job titles",
    titleExample: "Software Engineer…",
    location: "e.g. Austin, TX",
    roleAnchors: "Role keywords",
    excludeTerms: "Excluded terms",
    normalizing: "Standardizing locations…",
  },
};

const zh: typeof tagListEn = {
  add: "添加",
  addTo: "添加到{{field}}",
  added: "已添加 {{values}}。",
  alreadyAdded: "已添加过此值。",
  remove: "移除 {{value}}",
  removed: "已移除 {{value}}。",
  noMatches: "没有匹配项。仍可输入并添加。",
  pending: "保存前，请按 Enter 或点击“添加”来添加输入内容，或清空输入框。",
  suggestions: "{{field}}的建议",
  limit: "最多添加 {{count}} 个值。请移除已添加的值，或减少本次输入的数量。",
  repositories: {
    preferences: "导入偏好",
    search: "搜索仓库",
    name: "仓库名称",
    loading: "正在加载仓库…",
    unavailable: "暂时无法加载仓库。仍可输入并添加仓库名称。",
    include: "始终包含代码仓库",
    includeHelp: "这些仓库会跳过排名。",
    exclude: "排除代码仓库",
    excludeHelp: "导入时会跳过这些仓库。",
    limit: "代码仓库数量上限",
    limitHelp: "按排名导入的仓库数量上限，可设为 1 到 100。",
    invalidLimit: "请输入 1 到 100 之间的整数后保存。",
  },
  offers: {
    heading: "用于对比的录用通知",
    label: "录用通知",
    search: "公司、职位或申请 ID",
    help: "最多添加 10 份录用通知。",
    loading: "正在加载录用通知…",
    unavailable: "暂时无法加载录用通知。仍可输入职位申请 ID。",
    empty: "没有找到录用通知。仍可输入职位申请 ID。",
    invalid: "请选择录用通知，或输入已收到录用通知的申请 ID。",
  },
  search: {
    keywords: "关键词",
    keywordExample: "例如：分布式系统",
    titles: "职位名称",
    titleExample: "软件工程师…",
    location: "例如：Austin, TX",
    roleAnchors: "职位关键词",
    excludeTerms: "排除词",
    normalizing: "正在规范地点…",
  },
};

function register() {
  i18n.addResourceBundle("en", "translation", { tagList: tagListEn }, true, true);
  i18n.addResourceBundle("zh-CN", "translation", { tagList: zh }, true, true);
}

if (i18n.isInitialized) register();
else i18n.on("initialized", register);
