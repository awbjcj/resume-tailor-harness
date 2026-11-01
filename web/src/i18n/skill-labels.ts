const labels: Record<string, string> = {
  "Technical skills": "技术技能",
  "People & delivery": "协作与执行",
  "Industry knowledge": "行业知识",
  Other: "其他",
  "Programming Languages": "编程语言",
  "Frontend & Web": "前端与 Web",
  "Backend & APIs": "后端与 API",
  "Mobile & Desktop": "移动端与桌面端",
  "Data Engineering & Analytics": "数据工程与分析",
  "AI & Machine Learning": "AI 与机器学习",
  "Databases & Storage": "数据库与存储",
  "Cloud & Infrastructure": "云与基础设施",
  "DevOps & Automation": "DevOps 与自动化",
  "Testing & Quality": "测试与质量",
  "Security & Compliance": "安全与合规",
  "Systems & Embedded": "系统与嵌入式",
  "Architecture & Design": "架构与设计",
  "Tools & Platforms": "工具与平台",
  "Leadership & Management": "领导与管理",
  "Collaboration & Communication": "协作与沟通",
  "Product & Business": "产品与业务",
  "Process & Methodology": "流程与方法",
  "Domain Knowledge": "领域知识",
  "Years-of-experience requirement": "工作年限要求",
  "Education or degree requirement": "学历或学位要求",
  "Employment eligibility or clearance requirement": "工作资格或安全许可要求",
  "Travel or relocation requirement": "出差或搬迁要求",
  "Empty skill name": "技能名称为空",
};

export function localizeSkillLabel(
  label: string,
  language: string | undefined,
) {
  return language?.startsWith("zh") ? (labels[label] ?? label) : label;
}

/** User-authored labels remain exactly as entered, including familiar English names. */
export function localizeSkillContainer<
  T extends { label: string; customized?: boolean },
>(item: T, language: string | undefined): T {
  return item.customized
    ? item
    : { ...item, label: localizeSkillLabel(item.label, language) };
}
