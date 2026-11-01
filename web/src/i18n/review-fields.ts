import { useTranslation } from "react-i18next";
import { profileChangesEn, profileChangesZh } from "./profile-changes";

// Preview payloads use both snake_case and camelCase. Translate schema labels,
// never free-form titles, answers, evidence, URLs or other user-authored values.
const fields: Record<string, readonly [string, string]> = {
  id: ["Record ID", "记录编号"], job_id: ["Job ID", "职位编号"], target_id: ["Target ID", "目标编号"],
  note_id: ["Note ID", "笔记编号"], question_id: ["Question ID", "问题编号"], artifact_id: ["Document ID", "文档编号"],
  application_id: ["Application ID", "申请编号"], resume_version_id: ["Selected resume ID", "所选简历编号"],
  cover_letter_id: ["Selected cover letter ID", "所选求职信编号"],
  body: ["Note", "笔记内容"], notes: ["Notes", "备注"], content: ["Content", "内容"],
  reference: ["Reference", "参考信息"], question: ["Question", "问题"], answer: ["Answer", "答案"],
  scope: ["Applies to", "适用范围"], kind: ["Type", "类型"], status: ["Status", "状态"],
  application_status: ["Application status", "申请状态"], archived: ["Archived", "已归档"], deleted: ["Deleted", "已删除"],
  archived_at: ["Archived at", "归档时间"], created_at: ["Created at", "创建时间"], updated_at: ["Updated at", "更新时间"],
  applied_at: ["Applied at", "申请时间"], revision: ["Revision", "版本"], selected: ["Selected", "已选择"],
  jd_text: ["Job description", "职位描述"], source: ["Source", "来源"],
  custom_label: ["Event name", "事件名称"], sequence: ["Round", "轮次"], sequence_override: ["Custom round", "自定义轮次"],
  occurred_at: ["Date and time", "日期和时间"], all_day: ["All day", "全天"], timezone: ["Time zone", "时区"],
  duration_minutes: ["Duration (minutes)", "时长（分钟）"], modality: ["Meeting format", "会面方式"],
  platform: ["Platform", "平台"], platform_other: ["Other platform", "其他平台"],
  location_or_link: ["Location or meeting link", "地点或会议链接"], interviewers: ["Interviewers", "面试官"],
  result: ["Result", "结果"], reflection: ["Reflection", "复盘"],
  comp_base: ["Base salary", "基本工资"], comp_bonus: ["Annual bonus", "年度奖金"],
  comp_equity_annual: ["Equity per year", "年度股权"], comp_signing: ["Signing bonus", "签约奖金"],
  comp_currency: ["Currency", "币种"], total_comp: ["Total compensation", "薪酬总额"],
  keywords: ["Keywords", "关键词"], titles: ["Job titles", "职位名称"], locations: ["Locations", "地点"],
  remote_policy: ["Work arrangements", "办公方式"], min_salary: ["Minimum salary", "最低薪资"],
  yoe_min: ["Minimum years of experience", "最少工作年数"], yoe_max: ["Maximum years of experience", "最多工作年数"],
  sponsorship_required: ["Visa sponsorship required", "需要工作签证担保"], role_anchors: ["Role keywords", "职位关键词"],
  exclude_terms: ["Excluded terms", "排除词"], target_role: ["Target role", "目标职位"],
  distance: ["Search radius", "搜索半径"], max_days_old: ["Maximum posting age (days)", "职位发布天数上限"],
  experience_levels: ["Experience levels", "经验级别"], employment_types: ["Employment types", "雇佣类型"],
  full_name: ["Full name", "全名"], preferred_name: ["Preferred name", "常用名"], address: ["Address", "地址"],
  linkedin_url: ["LinkedIn URL", "LinkedIn 网址"], portfolio_url: ["Portfolio URL", "作品集网址"],
  expected_salary: ["Expected salary", "期望薪资"], sponsorship_needed: ["Sponsorship needed", "签证担保需求"],
  us_worker_category: ["US worker category", "美国工作身份类别"],
  work_authorization_verification: ["Work authorization documents", "工作资格证明"],
  availability: ["Availability", "可入职时间"], relocation: ["Relocation preference", "搬迁意愿"],
  remote_preference: ["Work arrangement preference", "办公方式偏好"],
  industry_experience: ["Industry experience", "行业工作经验"], coding_preference: ["Coding time preference", "编程时间偏好"],
  technical_domain: ["Preferred technical domain", "偏好的技术领域"], office_attendance: ["Office attendance", "到岗安排"],
  at_least_18: ["At least 18 years old", "已满 18 周岁"], termination_history: ["Termination history", "解雇记录"],
  export_control_citizenship: ["Citizenship for export controls", "出口管制所需的国籍信息"],
  planned_board_membership: ["Planned board memberships", "计划担任的董事职务"],
  current_board_membership: ["Current board memberships", "目前担任的董事职务"],
  government_employment: ["Government employment", "政府任职经历"], referral_sources: ["Referral sources", "职位来源"],
  previous_employment: ["Previous employment", "过往任职经历"], previous_applications: ["Previous applications", "过往申请记录"],
  employer_relationships: ["Employer relationships", "与雇主员工的关系"],
  employer_screening_answers: ["Employer screening answers", "雇主筛选问答"],
  pronouns: ["Pronouns", "称谓代词"], gender: ["Gender identity", "性别认同"], ethnicity: ["Ethnicity", "族裔"],
  veteran_status: ["Veteran status", "退伍军人身份"], disability_status: ["Disability status", "残障状况"],
  education_notes: ["Education notes", "教育背景备注"], experience_notes: ["Experience notes", "工作经历备注"],
  additional_answers: ["Additional answers", "补充答案"], legal_name: ["Legal name", "法定姓名"],
  preferred_name_parts: ["Preferred name", "常用名"], given_name: ["Given name", "名"], middle_name: ["Middle name", "中间名"],
  family_name: ["Family name", "姓"], suffix: ["Name suffix", "姓名后缀"], mailing_address: ["Mailing address", "邮寄地址"],
  line1: ["Address line 1", "地址第一行"], line2: ["Address line 2", "地址第二行"], city: ["City", "城市"],
  region: ["State / province / region", "州／省／地区"], postal_code: ["Postal code", "邮政编码"], country: ["Country", "国家"],
  alternate_emails: ["Alternate emails", "备用电子邮箱"], confirmed_on: ["Confirmed on", "确认日期"],
  permitted: ["May use for applications", "允许用于申请"], work_eligibility: ["Work eligibility", "工作资格"],
  employer: ["Employer", "雇主"], requisition: ["Requisition ID", "招聘编号"],
  immigration_status: ["Immigration status", "移民身份"], authorized_to_work: ["Legally authorized to work", "具有合法工作资格"],
  sponsorship_now: ["Needs sponsorship now", "目前需要签证担保"],
  sponsorship_future: ["Needs sponsorship in the future", "将来需要签证担保"],
  can_verify_authorization: ["Can verify right to work", "可提供工作资格证明"],
  currently_on_opt: ["Currently on OPT", "目前处于 OPT 期间"], stem_opt_extension_eligible: ["Eligible for STEM OPT", "符合 STEM OPT 延期资格"],
  experience_ranges: ["Experience ranges", "工作年限范围"], specialty: ["Specialty", "专业领域"],
  minimum_years: ["Minimum years", "最少年数"], maximum_years: ["Maximum years", "最多年数"],
  timeframe: ["Timeframe", "适用时间范围"], valid_until: ["Valid until", "有效期至"],
  employer_answers: ["Employer answers", "雇主问答"], sex: ["Sex", "生理性别"],
  sex_confirmed_on: ["Sex answer confirmed on", "生理性别答案确认日期"],
  ai_matching_preference: ["AI matching preference", "AI 匹配偏好"],
  ai_matching_confirmed_on: ["AI matching preference confirmed on", "AI 匹配偏好确认日期"],
  criteria_json: ["Extracted requirements", "提取的职位要求"], analysis_meta_json: ["Analysis details", "分析详情"],
  industry_pending: ["Industry review pending", "待确认行业"], reject_reason: ["Rejection reason", "排除原因"],
  reject_category: ["Rejection category", "排除类别"], gate_override: ["Requirement override", "放宽要求"],
  fit_score: ["Fit score", "匹配得分"], fit_rationale: ["Fit assessment", "匹配分析"],
  attempt: ["Attempt", "尝试次数"], round: ["Review round", "审核轮次"], review_score: ["Review score", "审核得分"],
  citations: ["Sources", "参考来源"], content_fingerprint: ["Content fingerprint", "内容标识"],
  content_json: ["Document content", "文档内容"], critique_json: ["Review feedback", "审核意见"],
  dedup_key: ["Duplicate detection key", "重复检测标识"], evidence_portfolio_json: ["Supporting evidence", "支持依据"],
  evidence_portfolio_status: ["Evidence status", "依据状态"], fact_check_passed: ["Fact check passed", "事实核验通过"],
  gate_reviewers_json: ["Required reviews", "必须通过的审核"], history: ["History", "历史记录"],
  identity: ["Identity", "身份信息"], instruction: ["Instructions", "说明"], origin: ["Origin", "原始来源"],
  parent_id: ["Parent record ID", "上级记录编号"], parent_version_id: ["Previous version ID", "上一版本编号"],
  pdf_path: ["PDF path", "PDF 路径"], posted_at: ["Posted at", "发布时间"], schema_version: ["Schema version", "数据格式版本"],
  skill_uses_json: ["Skills used", "使用的技能"], source_identity: ["Source identity", "来源标识"],
  submitted_at: ["Submitted at", "提交时间"], tailor_model: ["Tailoring model", "简历定制模型"],
  taxonomy_manifest_json: ["Skill classification details", "技能分类详情"], taxonomy_revision: ["Skill classification version", "技能分类版本"],
};

function normalizeField(key: string) {
  return key.replace(/([a-z0-9])([A-Z])/g, "$1_$2").toLowerCase();
}

export function localizeReviewField(key: string, language?: string, owner?: string) {
  const normalized = normalizeField(key);
  const chinese = language?.startsWith("zh");
  if (normalized === "name" && ["skill", "skills"].includes(owner ?? "")) return chinese ? "技能名称" : "Skill name";
  if (normalized === "name" && owner === "skill_category") return chinese ? "类别名称" : "Category name";
  if (normalized === "category" && owner === "employer_answers") return chinese ? "答案类别" : "Answer category";
  if (normalized === "title" && owner === "experience") return chinese ? "职位名称" : "Job title";
  const profileFields: Record<string, string> = chinese ? profileChangesZh.fields : profileChangesEn.fields;
  return fields[normalized]?.[chinese ? 1 : 0] ?? profileFields[normalized]
    ?? key.replace(/([a-z0-9])([A-Z])/g, "$1 $2").replaceAll("_", " ");
}

const enums: Record<string, Record<string, readonly [string, string]>> = {
  category: {
    hard: ["Hard skill", "硬技能"], soft: ["Soft skill", "软技能"], domain: ["Domain knowledge", "领域知识"], unspecified: ["Not specified", "未指定"],
    general: ["General screening", "一般筛选问题"], referral: ["Referral source", "职位来源"],
    employment: ["Employment history", "雇佣记录"], contractor: ["Contractor history", "承包／派遣工作记录"],
    relationship: ["Employer relationships", "与雇主员工的关系"], previous_application: ["Previous applications", "过往申请记录"],
    degree_category: ["Degree category", "学位类别"], role_requirement: ["Role requirement", "职位要求"],
  },
  scope: { job: ["This job", "此职位"], profile: ["Profile", "个人资料"] },
  ai_matching_preference: { unknown: ["Not specified", "未指定"], opt_in: ["Opt in", "选择加入"], opt_out: ["Opt out", "选择不加入"], ask: ["Ask each time", "每次询问"] },
  status: {
    raw: ["New", "新职位"], analyzed: ["Analyzed", "已分析"], shortlisted: ["Shortlisted", "已入围"], approved: ["Approved", "已批准"],
    tailored: ["Tailored", "已定制"], rendered: ["Rendered", "已生成文档"], rejected: ["Rejected", "已拒绝"],
    ready: ["Ready", "已就绪"], submitted: ["Submitted", "已提交"], applied: ["Applied", "已申请"],
    interview: ["Interview", "面试中"], offer: ["Offer", "已获录用意向"], closed: ["Closed", "已结束"],
  },
  result: { pending: ["Pending", "待确认"], advanced: ["Advanced", "已进入下一轮"], rejected: ["Rejected", "未通过"], no_response: ["No response", "暂无回复"], cancelled: ["Cancelled", "已取消"], withdrew: ["Withdrew", "已退出"] },
  modality: { onsite: ["In person", "现场"], virtual: ["Video call", "视频会议"], phone: ["Phone", "电话"], async: ["Asynchronous", "异步" ] },
  platform: {
    zoom: ["Zoom", "Zoom"], teams: ["Microsoft Teams", "Microsoft Teams"], google_meet: ["Google Meet", "Google Meet"],
    webex: ["Webex", "Webex"], tencent_meeting: ["Tencent Meeting", "腾讯会议"], feishu: ["Feishu", "飞书"],
    phone: ["Phone", "电话"], hackerrank: ["HackerRank", "HackerRank"], codesignal: ["CodeSignal", "CodeSignal"],
    coderpad: ["CoderPad", "CoderPad"], karat: ["Karat", "Karat"], other: ["Other", "其他"],
  },
  kind: {
    resume: ["Resume", "简历"], cover_letter: ["Cover letter", "求职信"], application_submitted: ["Application submitted", "已提交申请"],
    recruiter_screen: ["Recruiter screen", "招聘初筛"], online_assessment: ["Online assessment", "在线测评"], questionnaire: ["Questionnaire", "问卷"],
    technical_phone_screen: ["Technical phone screen", "技术电话初筛"], technical_round: ["Technical interview", "技术面试"],
    system_design: ["System design", "系统设计"], behavioral: ["Behavioral interview", "行为面试"], hiring_manager: ["Hiring manager interview", "用人经理面试"],
    onsite_loop: ["Onsite interviews", "现场面试"], team_match: ["Team matching", "团队匹配"],
    offer_received: ["Offer received", "收到录用意向"], offer_deadline: ["Offer deadline", "录用意向答复截止时间"],
    rejected: ["Rejection", "拒绝"], withdrawn: ["Application withdrawn", "已撤回申请"], custom: ["Custom event", "自定义事件"],
  },
};

export function localizeReviewEnum(value: string, field: string | undefined, language?: string) {
  const key = normalizeField(field ?? "");
  return enums[key === "application_status" ? "status" : key]?.[value]?.[language?.startsWith("zh") ? 1 : 0] ?? value;
}

export function useReviewValueCopy() {
  const { i18n } = useTranslation();
  const chinese = i18n.resolvedLanguage?.startsWith("zh");
  return {
    field: (key: string, owner?: string) => localizeReviewField(key, i18n.resolvedLanguage, owner),
    enumValue: (value: string, key?: string) => localizeReviewEnum(value, key, i18n.resolvedLanguage),
    normalizeField,
    none: chinese ? "未填写" : "Not set",
    emptyText: chinese ? "空文本" : "Empty text",
    emptyList: chinese ? "无条目" : "No entries",
    noFields: chinese ? "无字段" : "No fields",
    yes: chinese ? "是" : "Yes",
    no: chinese ? "否" : "No",
    before: chinese ? "更改前" : "Before",
    after: chinese ? "更改后" : "After",
    newItem: chinese ? "新增内容" : "New item",
    removedItem: chinese ? "将移除的内容" : "Item to remove",
  };
}
