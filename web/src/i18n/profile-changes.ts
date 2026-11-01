import i18n from "i18next";

export const profileChangesEn = {
  pending: "Needs approval", applied: "Applied", discarded: "Discarded",
  help: "Review the exact changes below. Your profile changes only after you apply them.",
  before: "Before", after: "After", empty: "None", evidence: "Your request",
  apply: "Apply changes", discard: "Discard", created: "New record", removed: "Removed",
  operations: { create: "Create", update: "Update", delete: "Remove" },
  removalHelp: "Source documents and conversations are kept. Rebuilding will not restore this profile.",
  yes: "Yes", no: "No",
  composer: "Ask to create, edit or remove profile facts, skills or categories…",
  description: "Build and manage your profile through conversation. Explore evidence, correct facts, organize skills, and review changes before applying them.",
  pendingEnd: "{{count}} pending drafts will remain unapplied.",
  fields: {
    profile: "Profile", skill: "Skill", skill_category: "Skill category",
    contact: "Contact", name: "Name", headline: "Headline", email: "Email", phone: "Phone",
    location: "Location", willing_to_relocate: "Willing to relocate", work_authorization: "Work authorization",
    links: "Links", label: "Label", url: "URL", summary: "Summary", interests: "Interests",
    company: "Company", title: "Title", employment_type: "Employment type", start: "Start", end: "End",
    current: "Current", bullets: "Evidence", tech: "Technologies", institution: "Institution",
    degree: "Degree", field: "Field", gpa: "GPA", honors: "Honors", relevant_coursework: "Relevant coursework",
    activities: "Activities", description: "Description", role: "Role", highlights: "Highlights",
    repo_url: "Repository", issuer: "Issuer", date: "Date", credential_id: "Credential ID",
    venue: "Venue", authors: "Authors", language: "Language", proficiency: "Proficiency",
    organization: "Organization", text: "Statement", aspect: "Aspect", aliases: "Aliases",
    context: "Context", category: "Skill type", experience: "Experience", education: "Education",
    projects: "Projects", skills: "Skills", certifications: "Certifications", publications: "Publications",
    awards: "Awards", languages: "Languages", volunteer: "Volunteering",
  },
};

export const profileChangesZh: typeof profileChangesEn = {
  pending: "待批准", applied: "已应用", discarded: "已丢弃",
  help: "请查看下方的具体更改。只有点击应用后，个人资料才会更新。",
  before: "更改前", after: "更改后", empty: "无", evidence: "你的请求",
  apply: "应用更改", discard: "丢弃", created: "新增记录", removed: "已移除",
  operations: { create: "创建", update: "更新", delete: "移除" },
  removalHelp: "源文档和对话将保留。重新构建不会恢复此个人资料。",
  yes: "是", no: "否",
  composer: "通过对话创建、编辑或移除个人资料事实、技能或分类…",
  description: "通过对话构建和管理个人资料。梳理证据、修正事实、整理技能，并在应用前审核更改。",
  pendingEnd: "{{count}} 份待处理草稿将保留，尚未应用。",
  fields: {
    profile: "个人资料", skill: "技能", skill_category: "技能分类",
    contact: "联系信息", name: "姓名", headline: "个人标题", email: "电子邮箱", phone: "电话",
    location: "所在地", willing_to_relocate: "愿意搬迁", work_authorization: "工作许可",
    links: "链接", label: "标签", url: "网址", summary: "简介", interests: "兴趣",
    company: "公司", title: "标题", employment_type: "雇佣类型", start: "开始", end: "结束",
    current: "目前在任", bullets: "事实证据", tech: "技术", institution: "学校",
    degree: "学位", field: "专业", gpa: "绩点", honors: "荣誉", relevant_coursework: "相关课程",
    activities: "活动", description: "描述", role: "角色", highlights: "亮点",
    repo_url: "代码仓库", issuer: "颁发机构", date: "日期", credential_id: "证书编号",
    venue: "发表平台", authors: "作者", language: "语言", proficiency: "熟练程度",
    organization: "组织", text: "陈述", aspect: "维度", aliases: "别名",
    context: "背景", category: "技能类型", experience: "工作经历", education: "教育经历",
    projects: "项目", skills: "技能", certifications: "证书", publications: "发表成果",
    awards: "奖项", languages: "语言", volunteer: "志愿经历",
  },
};

function registerTranslations() {
  i18n.addResourceBundle("en", "translation", { profileChanges: profileChangesEn }, true, true);
  i18n.addResourceBundle("zh-CN", "translation", { profileChanges: profileChangesZh }, true, true);
}

if (i18n.isInitialized) registerTranslations();
else i18n.on("initialized", registerTranslations);
