import fs from "node:fs";
import path from "node:path";
import { createHash } from "node:crypto";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

import { parse } from "@babel/parser";
import traverseModule from "@babel/traverse";

const traverse = traverseModule.default ?? traverseModule;
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const sourceRoot = path.join(root, "src");
const catalogPath = path.join(sourceRoot, "i18n", "auto-catalog.json");
const dynamicZhCNPath = path.join(sourceRoot, "i18n", "dynamic-zh-CN.json");
const backendSourceRoot = path.resolve(root, "..", "src", "resume_tailor_harness");
const runtimeCatalogPaths = {
  en: path.join(sourceRoot, "i18n", "auto-en.json"),
  "zh-CN": path.join(sourceRoot, "i18n", "auto-zh-CN.json"),
};
const require = createRequire(import.meta.url);
const {
  clean,
  isHumanText,
  isLocalizableStringPath,
  templateSource,
} = require("../i18n-classifier.cjs");

// These are the terms where product context matters more than a literal
// translation. They are deliberately authored and checked against the catalog;
// the catalog is never generated from a translation service.
const BASE_ZH_CN_TRANSLATIONS = {
  "Yes": "是",
  "No": "否",
  "Given name": "名",
  "Middle name": "中间名",
  "Family name": "姓",
  "Name suffix": "姓名后缀",
  "Address line 1": "地址第一行",
  "Address line 2": "地址第二行",
  "State / province / region": "州／省／地区",
  "Postal code": "邮政编码",
  "Address country": "地址所在国家",
  "Alternate email": "备用电子邮箱",
  "Employer (blank means all employers)": "雇主（留空表示适用于所有雇主）",
  "Requisition / role ID": "招聘／职位编号",
  "Applicable country": "适用国家",
  "May use for applications": "是否允许用于申请",
  "Confirmation date": "确认日期",
  "Immigration status": "移民身份",
  "Legally authorized to work": "是否具有合法工作资格",
  "Needs sponsorship now": "目前是否需要工作签证担保",
  "Needs sponsorship in the future": "将来是否需要工作签证担保",
  "Can verify legal right to work": "是否可提供合法工作资格证明",
  "Currently on OPT": "目前是否处于 OPT 期间",
  "Eligible for a STEM OPT extension": "是否符合 STEM OPT 延期资格",
  "Area of experience": "工作经验领域",
  "Minimum years": "最少年数",
  "Maximum years": "最多年数",
  "Employer": "雇主",
  "Answer category": "答案类别",
  "General screening": "一般筛选问题",
  "Referral source": "职位来源",
  "Employment history": "雇佣记录",
  "Contractor history": "承包／派遣工作记录",
  "Employer relationships": "与雇主员工的关系",
  "Application history": "申请记录",
  "Degree dropdown mapping": "学位下拉选项映射",
  "Role requirements": "职位要求",
  "Exact question or degree option details": "问题原文或学位选项说明",
  "Confirmed answer (blank means unknown)": "已确认的答案（留空表示未知）",
  "Applicable timeframe": "适用时间范围",
  "Valid until (optional)": "有效截止日期（可选）",
  "Names and mailing address": "姓名与邮寄地址",
  "Enter each part of your name and address as it should appear on applications. Blank fields stay unknown; your existing contact notes are kept.": "分别填写申请时要使用的姓名和地址各部分。留空表示未知，现有的联系信息备注会保留。",
  "Legal name": "法定姓名",
  "Preferred name": "常用姓名",
  "Alternate application emails": "申请备用邮箱",
  "Keep your primary email above. Use an alternate only with explicit permission and when its employer, requisition, and country limits match the application.": "上方保留主邮箱。只有明确允许，且雇主、招聘编号和适用国家与当前申请相符时，才可使用备用邮箱。",
  "Add alternate email": "添加备用邮箱",
  "Remove alternate email": "移除备用邮箱",
  "Work eligibility by country": "各国工作资格",
  "Record each country separately. Unknown does not mean No. Answer immigration status, work authorization, sponsorship, OPT, and STEM eligibility separately.": "分别记录各国情况。“未知”不代表“否”。移民身份、工作资格、签证担保、OPT 和 STEM 资格请分别回答。",
  "Add country eligibility": "添加国家工作资格",
  "Remove country eligibility": "移除国家工作资格",
  "Experience by specialty": "各领域工作年限",
  "Enter your own experience range for each specialty. Fill in both the minimum and maximum, or leave both blank. A range cannot stand in for an exact number of years and does not increase automatically over time.": "填写本人确认的各领域工作年限范围。最少和最多工作年数需同时填写，或同时留空。范围不能用作确切年数，也不会随时间自动增加。",
  "Add experience range": "添加工作年限范围",
  "Remove experience range": "移除工作年限范围",
  "Application defaults": "申请默认偏好",
  "Sex and gender are separate, optional disclosures. The AI preference covers optional candidate matching only. Confirm agreements and submission separately for each application.": "生理性别和性别认同是两项独立的自愿披露。AI 偏好仅适用于可选的候选人匹配；接受协议和提交申请仍需针对每份申请分别确认。",
  "Sex (optional self-identification)": "生理性别（自愿披露）",
  "Sex answer confirmation date": "生理性别答案确认日期",
  "AI-assisted candidate matching": "AI 辅助候选人匹配",
  "Opt in": "选择加入",
  "Opt out": "选择不加入",
  "Ask each time": "每次询问",
  "AI matching preference confirmation date": "AI 匹配偏好确认日期",
  "Employer answers": "雇主问答",
  "Save the exact wording and where each answer applies, including degree dropdown choices and role-specific answers. Leave the requisition blank to cover all roles at that employer. Keep your actual degree unchanged. Existing employer notes are below.": "保存问题、答案的原文及适用范围，包括学位下拉选项和特定职位的答案。招聘编号留空表示适用于该雇主的所有职位。请保留实际所获学位，现有的雇主备注仍在下方。",
  "Add employer answer": "添加雇主问答",
  "Remove employer answer": "移除雇主问答",
  "· {{v0}} paused after repeated attempts; narrow filters to retry": "· {{v0}} 项在多次尝试后已暂停；请缩小筛选范围后重试",
  "· run usage limit reached": "· 已达到本次运行的用量上限",
  "Clean up skills": "清理技能",
  "Review degrees, years of experience, and other requirements that are not skills. Discarded entries no longer appear in the skill map or participate in future regrouping. Original job descriptions stay intact, and entries can be restored.": "检查学位、工作年限等不属于技能的要求。排除后，条目不再出现在技能图谱中，也不参与后续分组。原始职位描述不变，条目可以恢复。",
  "Suggested non-skills": "建议排除的非技能条目",
  "All skill entries": "全部技能条目",
  "Search cleanup entries": "搜索待清理条目",
  "Search entries…": "搜索条目…",
  "{{v0}} entries · {{v1}} selected (up to 500)": "共 {{v0}} 个条目 · 已选 {{v1}} 个（最多 500 个）",
  "Select visible": "选择当前显示的条目",
  "Clear selection": "清除选择",
  "No matching entries. Use All skill entries to review other unwanted items.": "没有匹配的条目。切换到“全部技能条目”，查看其他需要排除的内容。",
  "Discard {{v0}}": "排除 {{v0}}",
  "Previous": "上一页",
  "Next": "下一页",
  "Discard selected ({{v0}})": "排除所选条目（{{v0}}）",
  "{{v0}} discarded non-skills": "{{v0}} 个已排除的非技能条目",
  "Discarded non-skills": "已排除的非技能条目",
  "These entries are excluded from skill demand and regrouping. Restore any valid entries.": "这些条目不再计入技能需求，也不参与重新分组。如有实际属于技能的条目，可以恢复。",
  "Search discarded entries": "搜索已排除的条目",
  "Showing {{v0}} of {{v1}} matching entries": "共 {{v1}} 个匹配条目，当前显示 {{v0}} 个",
  "Exclude this entry from skill demand and future regrouping. You can restore it from discarded non-skills. Original job descriptions stay intact.": "从技能需求和后续分组中排除此条目。可在“已排除的非技能条目”中恢复，原始职位描述不变。",
  "Selected entries discarded. You can restore them from discarded non-skills.": "已排除所选条目，可在“已排除的非技能条目”中恢复。",
  "Professional screening": "专业背景问答",
  "Save your own answers, not estimates from your resume. Date experience totals and specify the location and days per week for office attendance.": "请填写本人确认的答案，不要按简历推算。工作年限请注明确认日期，到岗安排请注明地点及每周天数。",
  "Years of industry experience": "行业工作年限",
  "e.g. 3 years, confirmed 2026-10-23": "例如：3 年，确认于 2026-10-23",
  "Coding time preference": "偏好的编程时间比例",
  "e.g. I generally enjoy spending 80% of my time coding": "例如：通常希望将 80% 的工作时间用于编程",
  "Preferred technical domain": "偏好的技术领域",
  "e.g. Full Stack — preferred and strongest domain": "例如：全栈——最偏好且最擅长的领域",
  "Office attendance": "到岗办公安排",
  "Country, office location, and days per week": "国家、办公地点及每周到岗天数",
  "Other employer-specific screening answers": "其他针对特定雇主的筛选问答",
  "Employer, role/requisition, exact answer, and confirmation date; include rolling application windows or role-specific start dates": "填写雇主、职位／招聘编号、确切回答和确认日期，以及滚动申请时间范围或该职位的入职日期",
  "100% · {{v0}}": "{{v0}}（100%）",
  "100% · done": "100% · 已完成",
  "A gated reviewer blocks the round outright, so it is never scored — its weight and score bands are disabled rather than silently ignored.": "启用硬性门槛的评审会直接阻断本轮，因此不参与评分；其权重和评分区间会被禁用，而非悄然忽略。",
  "Application timeline grid": "申请时间线表格",
  "Ask the Scout": "咨询职位探索助手",
  "Any annual salary": "不限年薪",
  "Apps": "应用",
  "Annual bonus": "年度奖金",
  "Avg fit in view": "当前视图平均匹配度",
  "Awaiting review": "等待审核",
  "Base": "基本工资",
  "Base salary": "基本工资",
  "Blocking — any claim not traceable to a profile fact fails the round.": "阻断项——任何无法追溯到个人资料事实的表述都将导致本轮不通过。",
  "Certified filings": "已认证申报数",
  "Choose a member": "选择成员",
  "Choose a tailored job. Jobs with an interview in progress are hidden so you can resume them from the sessions list.": "选择已有定制简历的职位。面试进行中的职位不在此列出，可从会话列表继续。",
  "Choose a tier": "选择档位",
  "Career Lab": "职业实验室",
  "Confidence": "置信度",
  "Complete": "已完成",
  "Collapse": "收起",
  "Could not add": "无法添加",
  "Coverage of the job description's stated requirements.": "简历覆盖了多少职位描述中明确提出的要求。",
  "Create Scout session": "创建职位探索助手会话",
  "Data version": "数据版本",
  "Deleted {{v0}} cover letter{{v1}}": "已删除 {{v0}} 封求职信",
  "Deleted {{v0}} version{{v1}}": "已删除 {{v0}} 个简历版本",
  "Density — cuts padding without cutting evidence.": "信息密度——精简冗余，同时保留证据。",
  "Depth and credibility of the evidence for this specific role.": "支持这个职位的经历依据是否充分、可信。",
  "Describe the search": "说明搜索条件",
  "Discovery goal": "职位探索目标",
  "Discovery request": "职位探索请求",
  "Discovery Scout": "职位探索助手",
  "Discovery Scout is unavailable": "职位探索助手暂不可用",
  "Discovery Scout sessions": "职位探索助手会话",
  "Drafting now": "正在起草",
  "Distinct skills": "去重后的技能数",
  "Drafting studio": "草稿编辑区",
  "Domain updated": "领域已更新",
  "Domains merged": "领域已合并",
  "Equity per year": "年度股权",
  "Equity / year": "年度股权",
  "Enter a non-negative annual salary.": "请输入不小于零的年薪。",
  "Expires": "到期时间",
  "Expand": "展开",
  "Export grid": "导出表格",
  "Filing periods": "申报期间",
  "Filings": "申报数",
  "Fit >= {{v0}}": "匹配度 ≥ {{v0}}",
  "Fit <= {{v0}}": "匹配度 ≤ {{v0}}",
  "Fit band": "匹配度区间",
  "Filtered jobs": "筛选后的职位",
  "Focused rehearsal": "专项面试练习",
  "Generate another": "再生成一封",
  "Generate cover letter": "生成求职信",
  "Gate": "硬性门槛",
  "Gmail connected.": "Gmail 已连接。",
  "Guided discovery": "引导式职位探索",
  "Guided evidence discovery": "引导梳理真实经历",
  "Job": "职位",
  "job": "职位",
  "Jobs": "职位",
  "Integrity gate — read-only": "完整性校验（只读）",
  "Listen first, with interviewer text hidden until you reveal it.": "先听面试官提问，需要时再显示文字。",
  "Loading gap-closing advice": "正在加载学习建议",
  "Loaded": "已加载",
  "Message": "消息",
  "Matching": "匹配数",
  "Min salary (USD)": "最低年薪（美元）",
  "Mid tier model": "标准型模型",
  "Model tier": "模型档位",
  "Model tiers": "模型档位",
  "Model versions are grouped together, with the newest first. Saved versions cannot be changed. Sorting a column orders models by their latest version.": "同一模型的版本集中显示，保存后不可修改，最新版本排在前面。按任意列排序时，会根据各模型最新版本的数据排列模型组。",
  "Mock Interview": "模拟面试",
  "Mock Interviews": "模拟面试",
  "Must": "必须项",
  "Nice": "加分项",
  "No date": "无日期",
  "No saved research": "暂无已保存的调研结果",
  "Not reported": "未提供",
  "Not shown": "未体现",
  "Open gaps": "尚未弥补的差距",
  "Offer": "录用通知",
  "Offer %": "录用通知占比",
  "Offer application ids": "录用通知对应的申请 ID",
  "Offer comparison": "录用通知对比",
  "Offer comparison references": "录用通知对比参考",
  "Offer deadline": "录用回复截止日期",
  "Offer deadline: {{v0}}": "录用回复截止日期：{{v0}}",
  "Offer received": "已收到录用通知",
  "Offers": "录用通知",
  "offer": "录用通知",
  "Nothing is waiting on you": "目前没有需要你处理的事项",
  "New Scout session": "新建职位探索助手会话",
  "No Scout sessions yet. Start one when you are ready to shape your search.": "还没有职位探索助手会话。准备好明确求职方向时，即可开始一次探索。",
  "Per-pull job limit for {{v0}}": "{{v0}} 每次获取的职位上限",
  "Premium": "高价位",
  "Premium tier model": "高级型模型",
  "Proposal": "建议",
  "Profile Coach": "个人资料助手",
  "Pull jobs": "获取职位",
  "Question {{v0}} of {{v1}}": "第 {{v0}} 题，共 {{v1}} 题",
  "Queued": "已排队",
  "Related experience": "相关经历",
  "Researching": "调研中",
  "Review the research": "查看调研结果",
  "Retrieved": "获取时间",
  "Rendered in view": "当前视图已生成",
  "Salary >= {{v0}}": "薪资 ≥ {{v0}}",
  "Scored {{v0}}/5": "评分 {{v0}}/5",
  "Share of evidenced must-have requirements actually rendered.": "有证据支持且实际呈现的必备要求占比。",
  "Signing bonus": "签约奖金",
  "Signing": "签约奖金",
  "Scout could not reply": "职位探索助手未能回复",
  "Scout could not start": "职位探索助手无法启动",
  "Scout proposals": "职位探索助手建议",
  "Scout request failed": "职位探索助手请求失败",
  "Scout researching": "职位探索助手正在调研",
  "Shape a smarter search": "让搜索更精准",
  "Skill added": "技能已添加",
  "Skill moved": "技能已移动",
  "Skill removed": "技能已移除",
  "Skills merged": "技能已合并",
  "Sources tracked": "已跟踪来源",
  "Sponsorship offered in view": "当前视图中提供担保的职位数",
  "Stages active": "活跃阶段数",
  "Tell the Scout what you want to find. It will research companies and search terms, then wait for your approval before changing anything.": "告诉职位探索助手你想寻找什么。它会调研公司和搜索词，并在更改任何设置前等待你的批准。",
  "The Scout could not finish that step": "职位探索助手未能完成这一步",
  "The Scout returns separate, cited proposals instead of changing settings silently.": "职位探索助手会给出彼此独立且附带引用的建议，不会在未告知的情况下更改设置。",
  "Six-second skim: does the top of the page land?": "招聘人员快速看六秒，能否从简历顶部抓住重点？",
  "Supported": "有依据",
  "Select {{v0}} {{v1}}": "选择 {{v0}} {{v1}}",
  "Tech {{v0}}": "技术面试 {{v0}}",
  "Tech": "技术",
  "not scored": "不计分",
  "Warnings": "注意事项",
  "Warm": "亲和",
  "{{v0}} / {{v1}}": "{{v0}} / {{v1}}",
  "{{v0}} · stale": "{{v0}} · 已过时",
  "{{v0}} {{v1}}: {{v2}}": "{{v0}} {{v1}}：{{v2}}",
  "{{v0}} job{{v1}}": "{{v0}} 个职位",
  "{{v0}} percent": "百分之 {{v0}}",
  "{{v0}} turns": "{{v0}} 轮对话",
  "{{v0}}h": "{{v0}} 小时",
  "{{v0}}h {{v1}}m": "{{v0}} 小时 {{v1}} 分钟",
  "{{v0}}m": "{{v0}} 分钟",
  "{{v0}}% · {{v1}}": "{{v1}}（{{v0}}%）",
  "· ~{{v0}} left": " · 约剩 {{v0}}",
  "· {{v0}} skipped": "· 已跳过 {{v0}} 项",
  "({{v0}} pending)": "（{{v0}} 个待处理）",
  "Bonus": "奖金",
  "cover letter": "求职信",
  "done": "已完成",
  "every {{v0}}": "每 {{v0}}",
  "every {{v0}} {{v1}}s": "每 {{v0}} {{v1}}",
  "Keep {{v0}}": "保持 {{v0}}",
  "Local time {{v0}} {{v1}} does not exist in {{v2}}": "{{v2}} 时区不存在本地时间 {{v0}} {{v1}}",
  "resume version": "简历版本",
  "stage": "阶段",
  "Untitled Scout session": "未命名职位探索助手会话",
  "${{v0}}+ / year": "${{v0}}+ / 年",
  "${{v0}}k+ / year": "${{v0}}k+ / 年",
  "${{v0}}M+ / year": "${{v0}}M+ / 年",
  "{{v0}} job{{v1}} waiting on you": "有 {{v0}} 个职位等待你处理",
  "{{v0}} gate": "{{v0}} 硬性门槛",
  "{{v0}} model tier": "{{v0}} 模型档位",
  "{{v0}}…": "{{v0}}…",
  "Your browser blocked autoplay. Press play to listen.": "浏览器阻止了自动播放。请点击播放以收听。",
  "Corroborated": "多来源印证",
  "Single source": "单一来源",
  "Inference": "推断",
  "Company official": "公司官方来源",
  "Government or regulatory": "政府或监管来源",
  "Reputable independent": "可信独立来源",
  "Employee or community": "员工或社区来源",
  "Other public source": "其他公开来源",
  "Conflicting evidence:": "存在冲突的证据：",
  "Published": "发布时间",
  "research": "调研",
  "Version": "版本",
  "What changed": "本次变化",
  "Added {{v0}} source(s)": "新增 {{v0}} 个来源",
  "Removed {{v0}} source(s)": "已移除 {{v0}} 个来源",
  "No material evidence changes were detected.": "未发现实质性证据变化。",
  "Research history": "调研历史",
  "Loading history…": "正在加载调研历史…",
  "Quick scan prioritizes the strongest official and current independent evidence.": "快速调研优先查看可靠的官方资料和近期独立来源。",
  "Standard research balances coverage and cost across all supported research areas.": "标准调研会覆盖所有支持的调研维度，同时兼顾费用。",
  "Deep seeks corroboration, dates, and credible conflicting evidence.": "深度调研会核对多个来源和日期，也会查找可信的相反证据。",
  "{{v0}} Refreshing updates every job at this company.": "{{v0}} 刷新后会更新该公司的所有职位。",
  "Company research depth": "公司研究深度",
  "Quick": "快速",
  "Job-specific planning": "职位专项规划",
  "Role preparation": "面试准备",
  "Turn the frozen company dossier, exact job description, selected documents, and earlier-round notes into an interview-ready brief.": "根据冻结的公司档案、准确的职位描述、已选文档和前序面试记录生成可直接用于面试的准备简报。",
  "Generate a brief when you are ready. Saved briefs stay unchanged until you regenerate them.": "准备好后即可生成提纲。已保存的提纲会保持不变，直到你重新生成。",
  "Regenerate brief": "重新生成提纲",
  "Generate brief": "生成提纲",
  "Role preparation failed. The last saved brief is unchanged.": "面试准备提纲生成失败，上次保存的提纲仍然保留。",
  "Loading role preparation…": "正在加载面试准备提纲…",
  "Company research v": "公司研究版本",
  "Resume v": "简历版本",
  "Inputs changed": "参考资料已变更",
  "Generated": "生成时间",
  "The job, selected documents, company dossier, or interview notes changed after this brief was generated. The saved brief remains unchanged until you regenerate it.": "生成提纲后，职位、所选文档、公司档案或面试记录已有变化。重新生成前，保存的提纲不会更新。",
  "Earlier-round focus": "之前面试的重点",
  "Priority competencies": "重点考察的能力",
  "Concerns to prepare": "需要准备应对的问题",
  "Likely questions": "可能的问题",
  "Story prompt:": "案例提示：",
  "Questions to ask": "向面试官提问",
  "Recruiter verification": "向招聘人员确认",
  "No role brief yet": "暂无面试准备提纲",
  "Generate company research first, then build a role-specific brief.": "先完成公司调研，再生成针对这个职位的面试准备提纲。",
  "{{v0}} copied": "已复制{{v0}}",
  "Copy {{v0}}": "复制{{v0}}",
  "Copy": "复制",
  "Single public source": "单一公开来源",
  "Public source": "公开来源",
  "Email draft": "邮件草稿",
  "Short message draft": "短消息草稿",
  "Public-source people research": "通过公开资料调研联系人",
  "Hiring contacts": "招聘联系人",
  "Find people whose identities can be verified through public sources and who may be relevant to this role, then prepare drafts to copy.": "查找可能与此职位相关、身份可由公开来源核实的联系人，再生成供复制使用的消息草稿。",
  "No private enrichment, login-gated scraping, or automatic outreach.": "不补充私人数据，不抓取需要登录的页面，也不会自动联系任何人。",
  "Refresh contacts": "刷新联系人",
  "Research contacts": "调研联系人",
  "Draft only. This feature never sends messages. Verify every person's current role before use.": "这里只生成草稿，不会发送消息。使用前请核实联系人的当前职位。",
  "Contact research failed. The last saved result is unchanged.": "联系人调研失败，上次保存的结果仍然保留。",
  "No named contact was confirmed from public sources.": "未能通过公开来源核实具体联系人的身份。",
  "Role-addressed drafts": "发给招聘岗位联系人的草稿",
  "Use these when no named person is verified or when a general recruiting channel is more appropriate.": "还没核实具体联系人，或更适合通过通用招聘渠道联系时，可以使用这些草稿。",
  "Generic email draft": "通用邮件草稿",
  "Generic short message": "通用短消息",
  "No contact research yet": "暂无联系人调研",
  "Loading hiring-contact intelligence…": "正在加载招聘联系人情报…",
  "Compare up to three roles at a time": "一次最多比较三个职位",
  "Role comparison controls": "职位对比操作",
  "Compare roles": "对比职位",
  "Select two or three application rows. {{v0}} selected.": "请选择两到三条申请记录。已选择 {{v0}} 条。",
  "Comparing…": "正在比较…",
  "Compare selected": "对比所选职位",
  "Role comparison could not be loaded. The selected applications are unchanged.": "无法加载职位对比，所选申请仍然保留。",
  "Compare": "对比",
  "Select {{v0}} {{v1}} for comparison": "选择 {{v0}} 的 {{v1}} 进行对比",
  "Stored evidence only": "仅使用已存证据",
  "Role comparison": "职位对比",
  "Missing values stay explicit; this table does not call a model or guess an answer.": "缺失的信息会明确标出，这张表不会调用模型推测答案。",
  "Company evidence": "公司证据",
  "H-1B evidence": "H-1B 证据",
  "Latest offer": "最新录用通知",
  "Unknown role": "未知职位",
  "Not scored": "未评分",
  "No structured offer": "尚未记录录用通知的具体信息",
};

const HUMANIZED_ZH_CN_TRANSLATIONS = {
  "(may be out of date)": "（可能已过时）",
  "(unavailable)": "（不可用）",
  "A thread for this job is open. Continue it from the list below.": "这个职位已有进行中的对话，可从下方列表继续。",
  "Answer as you would in an interview. The questions adapt to your responses, and the completed rehearsal includes coaching.": "像参加正式面试一样作答。问题会根据你的回答调整，演练结束后会提供辅导建议。",
  "End the loop when a round scores below the best so far. This preserves the remaining rounds.": "某轮得分低于之前的最高分时，停止继续修改，保留剩余轮次。",
  "If a gated reviewer fails, the round fails regardless of its score. Gate reviewers do not contribute a score, so their weight and score bands are disabled.": "硬性门槛评审未通过时，无论本轮得分如何，本轮都不通过。门槛评审不参与评分，因此无法设置权重和评分区间。",
  "Aim for this number. It is not a hard cap. The skills section renders compact comma-separated categories; long names can wrap. Preserve evidenced must-have skills and remove redundant supporting entries before cutting work or project evidence.": "这是目标数量，并非硬性上限。技能按类别以逗号紧凑排列，较长名称可能换行。优先保留有证据支持的必备技能；先删除冗余的辅助条目，再考虑精简工作和项目证据。",
  "An interview for this job is in progress. Resume it from the list below.": "这个职位的面试正在进行，可从下方列表继续。",
  "Ask about this role with the job description in context. Get help with application answers, outreach, or negotiation prep, and keep every thread here.": "结合职位描述讨论该职位。你可以准备申请回复、外联沟通或谈判，并在这里保留所有对话。",
  "Blocking: any claim not traceable to a profile fact fails the round.": "真实性要求：每项表述都必须有个人资料中的事实依据，否则本轮不通过。",
  "Clear this workspace's data. Configuration, API keys, and sources are kept until you reset them explicitly. Hand-written profile overrides are always kept.": "清除工作区数据。配置、API 密钥和来源需单独重置；手动填写的个人资料覆盖项始终保留。",
  "Configuration, API keys, and hand-written profile overrides will not be removed.": "配置、API 密钥和手动填写的个人资料覆盖项会保留。",
  "Concision: remove padding while keeping evidence.": "删去冗余表达，保留有依据的内容。",
  "Connected ({{v0}} client). Reconnect to enable drafts.": "已连接（{{v0}} 客户端）。重新连接后可启用草稿功能。",
  "Connected ({{v0}} client). Sync and drafts are enabled.": "已连接（{{v0}} 客户端）。已启用同步和草稿功能。",
  "Compare role requirements with evidence in your profile, then identify skills to develop.": "对照职位要求和个人资料中的经历依据，找出需要提升的技能。",
  "Couldn’t connect Gmail. The sign-in didn’t complete. Please try again.": "无法连接 Gmail。登录未完成，请重试。",
  "Custom uploaded templates are kept. Reset them separately below.": "自定义上传的模板会保留。请在下方单独重置。",
  "Drop a document here. Accepted formats: PDF, DOCX, TXT, or Markdown. Maximum size: 15 MB.": "将文档拖放到此处。支持 PDF、DOCX、TXT 或 Markdown。最大 15 MB。",
  "Each entry should cover different types of contribution, such as scope, impact, or technique.": "每段经历应体现不同方面的贡献，比如负责的范围、取得的成果或采用的技术。",
  "Experience used and why": "选用了哪些经历，为什么",
  "Extracted facts, skill matrix, and fragments. Source documents and hand-written overrides stay.": "清除已提取的经历、技能矩阵和文档片段，保留源文档和手动修正的个人资料。",
  "Fact-lock failed: {{v0}}": "事实锁定失败：{{v0}}",
  "Used by the writer, reviser, and advisory panel. Minimums stay within the evidence in your profile, so they do not require invented claims. Rendering selects one or two pages. One-page drafts use lower bullet limits and preserve space for experience and projects.": "供撰写、修订和评审使用。最低条目数以档案中的实际证据为限，不会要求编造经历。在“渲染”设置中选择一页或两页；单页草稿会降低要点数量上限，为工作经历和项目保留空间。",
  "Integrity gate (read-only)": "完整性校验（只读）",
  "Merges, splits, renames, and recategorizes domains. Use Regroup to assign unassigned skills.": "合并、拆分、重命名技能领域，或调整其所属分类。未归类的技能请使用“重新分组”处理。",
  "Move your customizations between installs. A bundle includes only the settings below. It never includes your jobs, profile, or API keys.": "将自定义设置迁移到其他安装环境。设置包只包含下列设置，不含职位、个人资料或 API 密钥。",
  "Needed for tailoring. Everything else works without it.": "定制简历需要此项，其他功能不受影响。",
  "No documents yet. Start with your resume, the document that matters most.": "暂无文档。先添加简历，它是最重要的一份。",
  "No documents yet. Add your resume to get started.": "暂无文档。先添加简历即可开始。",
  "No coaching sessions yet. Start one to explore evidence for your profile.": "还没有辅导会话。开始一次对话，梳理能补充到个人资料的真实经历。",
  "No saved Career Lab sessions yet. Start one to create a draft.": "职业实验室还没有保存的会话。开始一次对话，写出第一份草稿。",
  "No Scout sessions yet. Start one to refine your search.": "还没有职位探索助手会话。开始一次对话，细化你的搜索条件。",
  "No jobs are ready for interview practice. Tailor a resume first.": "暂无可用于面试练习的职位。请先定制一份简历。",
  "No sources yet. Add your resume first; it becomes your primary source.": "暂无来源。请先添加简历，它将成为主要来源。",
  "Off-peak rates are active until {{v0}} UTC. Weekday peak hours are 01:00–04:00 and 06:00–10:00 UTC.": "当前为非高峰计费时段，持续至 {{v0}} UTC。工作日高峰时段为 01:00–04:00 和 06:00–10:00 UTC。",
  "Loading hiring contacts…": "正在加载招聘联系人…",
  "Set your search direction": "明确求职方向",
  "The Scout returns separate proposals with citations. It waits for your approval before changing settings.": "职位探索助手会逐项给出建议并附上来源。你批准后，它才会更改设置。",
  "Optional. Adds public repositories to your project facts.": "可选。将公开仓库纳入项目经历资料。",
  "Peak rates are active until {{v0}} UTC.": "当前为高峰计费时段，持续至 {{v0}} UTC。",
  "Profile built:": "个人资料已生成：",
  "Practice questions for a role with a tailored resume, then review a scored debrief.": "选择已有定制简历的职位进行面试练习，结束后查看评分和复盘。",
  "Practice realistic questions and review a scored debrief.": "练习真实面试中可能遇到的问题，再查看评分和复盘。",
  "Profile gap: not yet in your profile": "个人资料中尚未体现这项技能",
  "Set a search and enable at least one source so the agent knows where to look.": "设置搜索条件，并启用至少一个职位来源，助手才能开始查找。",
  "Answer each question while the coach follows up on useful details.": "逐一回答问题，教练会根据有用的细节继续追问。",
  "Select a job with a tailored resume so the questions reflect the role.": "选择已有定制简历的职位，让问题贴合该职位。",
  "The default weights are calibrated. Change them only when you have a clear reason.": "默认权重已经过校准。只有在理由明确时才调整它们。",
  "Review strengths, gaps, and better answer patterns after the rehearsal.": "演练结束后，看看哪些回答得好、哪里有不足，以及下次怎样回答。",
  "There is not enough forward stage history to show this chart. Repeated and out-of-order entries remain in the timeline without affecting it.": "申请阶段的进展记录还不够，暂时无法显示图表。重复或顺序异常的记录会保留在时间线中，不影响图表。",
  "There is not enough history yet. Consecutive dated stages will appear here.": "记录还不够。添加有日期的连续阶段后，即可在这里查看。",
  "There is not enough history yet. Log a few stages to see where applications go.": "历史记录不足。记录几个阶段后即可查看申请的进展。",
  "This interview is still in progress. Deleting it ends the interview without a debrief. This cannot be undone.": "此次面试仍在进行中。删除后将结束面试，且不会生成复盘。此操作无法撤销。",
  "This job has progress, so you cannot delete it.": "该职位已有进展，因此无法删除。",
  "This secret pairs with the client ID above. Set both together.": "此密钥与上方的客户端 ID 配套使用，请同时设置。",
  "This skill is not yet detected on your profile. Add it to clear the gap.": "个人资料中还没找到这项技能，补充后即可消除这项差距。",
  "Transcription failed. Tap Retry.": "转录失败。请点按“重试”。",
  "Upload a resume. The profile is built from it.": "上传简历，个人资料将根据简历生成。",
  "Used when \"Deep review\" is selected while tailoring. It has a separate saved roster.": "定制简历时选择“深度评审”，就会使用这套单独保存的评审配置。",
  "House style for tailored bullets. The tailor and reviewers use it.": "定制简历要点的写作规范，供写作和评审助手使用。",
  "Review each built-in prompt and add supporting guidance. Guidance can shape tone, emphasis, and process. It cannot change facts or integrity rules.": "查看内置提示词，并添加补充说明。可以调整语气、重点和处理流程，但不能更改事实或真实性规则。",
  "Create an interview brief from the frozen company dossier, job description, selected documents, and earlier interview notes.": "根据冻结的公司档案、职位描述、已选文档和前序面试记录创建面试准备简报。",
  "These entries did not name a skill, so they no longer use a classification call. Restore any valid entries.": "这些条目没有明确的技能名称，因此不会再调用模型分类。有效的条目可以手动恢复。",
  "Upload files, add notes or public pages, and sync GitHub projects. Your profile keeps the source evidence.": "上传文件，添加笔记或公开页面，并同步 GitHub 项目。个人资料会保留这些来源证据。",
  "Re-run the full funnel for one scope. Fit scores and statuses may change. Jobs with progress are not changed.": "在所选范围内重新运行完整筛选流程，匹配分数和状态可能会变化。已有进展的职位会保留原样。",
  "Discuss this role with the job description as context. Use this thread for application answers, outreach, or negotiation preparation.": "结合职位描述讨论这个职位。可在此对话中处理申请回复、外联沟通或谈判准备。",
  "Describe the companies, roles, locations, and boundaries for your search. Nothing is added until you approve it.": "说说你想找的公司、职位和地点，以及需要排除的条件。你批准后才会添加。",
  "Describe what you want to find. Scout researches companies and search terms, then waits for your approval before changing anything.": "说说你想找什么。职位探索助手会调研公司和搜索词，等你批准后才会作出任何更改。",
  "Add or dismiss each company and search term yourself.": "自行添加或忽略每个公司和搜索词。",
  "with the shipped default. Your current values will be lost. Export a settings bundle first if you may need them later.": "恢复为出厂默认值。你当前的设置将丢失。如有可能需要恢复，请先导出设置包。",
};

const FIXED_ZH_CN_TRANSLATIONS = {
  ...BASE_ZH_CN_TRANSLATIONS,
  ...HUMANIZED_ZH_CN_TRANSLATIONS,
  // Context-sensitive copy: job roles, settings backups, and AI usage must not
  // inherit the translations of account roles, fallback models, or credentials.
  "Agent activity": "助手动态",
  "Agent prompts": "助手提示词",
  "Couldn't load agent prompts": "无法加载助手提示词",
  "Reset this agent": "重置此助手",
  "Review the agent's summarized approach": "查看助手的处理思路",
  "Apps": "申请数",
  "Apply bundle": "导入设置包",
  "Backup": "备份",
  "Bundled": "内置",
  "Choose a role": "选择职位",
  "Role anchors": "目标职位关键词",
  "Role context": "职位背景",
  "Roles (": "职位 (",
  "Target role": "目标职位",
  "Untitled role": "未命名职位",
  "Why this role fits": "此职位适合你的原因",
  "Share roles, locations, industries, and boundaries in plain language.": "说说你想找的职位、地点、行业，以及需要排除的条件。",
  "What discovery looks for.": "设置要搜索的职位。",
  "Set the roles to search for. More specific role keywords help reduce irrelevant results.": "设置要搜索的职位。目标职位关键词越具体，获取的无关职位就越少。",
  "Tokens": "Token 用量",
  "Tokens, jobs, and concurrency": "Token 用量、职位数与并发数",
  "Terms emphasized": "重点突出的关键词",
  "Cost quotas": "费用配额",
  "Rendering": "简历输出",
  "Rendering options": "简历输出选项",
  "Pruning": "职位清理",
  "Roster": "评审配置",
  "Weighted panel score a round must reach to stop early.": "本轮简历的加权评审分数达到此值后，即可提前结束修改。",
  "Combining reviews saves time and cost. Turn this off to run each advisory reviewer separately.": "合并评审可减少耗时和费用；关闭后，各项评审将分别运行。",
  "Company intelligence": "公司调研",
  "Company research depth": "公司调研深度",
  "Company research v": "公司调研版本",
  "Start research": "开始调研",
  "Cold outreach": "首次联系",
  "Assistant response streaming": "助手正在回复",
  "Dashboard controls": "求职概览操作",
  "Evidence agenda": "待补充的经历",
  "Fact-lock failed": "简历真实性校验未通过",
  "Fact-lock failed: {{v0}}": "简历真实性校验未通过：{{v0}}",
  "Fact-lock passed": "简历真实性校验已通过",
  "+{{v0}} more supporting fact{{v1}}": "另有 {{v0}} 条经历依据",
  "new grounded facts": "新增的经历依据",
  "Profile facts built": "个人经历已整理",
  "Open coach": "打开个人资料助手",
  "Answer each question while the coach follows up on useful details.": "逐一回答问题，个人资料助手会继续追问相关细节。",
  "The coach could not finish that step": "个人资料助手未能完成这一步",
  "The coach is reviewing your evidence…": "个人资料助手正在查看你的经历…",
  "The coach reviews your current facts, asks one focused question at a time, and drafts only claims grounded in your answers.": "个人资料助手会先查看已有经历，每次问一个具体问题，只整理有你的回答作为依据的内容。",
  "The coach will prepare a recap and close the thread.": "个人资料助手会整理本次对话摘要，然后结束对话。",
  "Start your first coaching session to uncover grounded profile evidence.": "开始第一次资料梳理，补充能写进简历的真实经历。",
  "Turn overlooked outcomes, scope, and project evidence into grounded profile notes.": "梳理容易遗漏的成果、职责范围和项目细节，补充到个人资料中。",
  "Draft one from your profile facts and this job description. You can revise it afterwards.": "根据你的真实经历和这份职位描述生成草稿，之后可以继续修改。",
  "Create an interview brief from the frozen company dossier, job description, selected documents, and earlier interview notes.": "根据已保存的公司档案快照、职位描述、所选文档和之前的面试记录，生成面试准备提纲。",
  "Discuss this role with the job description as context. Use this thread for application answers, outreach, or negotiation preparation.": "结合职位描述讨论这个职位，准备申请问题的回答、联系邮件或谈判方案。",
  "Check employer filing history without changing the posting’s current sponsorship signal.": "查看雇主的历史申请记录。此操作不会更改职位上标注的签证担保信息。",
  "Start a thread anchored to": "围绕以下职位开始对话：",
  "Transcription failed. Tap Retry.": "语音转文字失败，请点击重试。",
  "Transcription failed": "语音转文字失败",
  "Transcribing": "正在转为文字",
  "Retry transcription": "重试语音转文字",
  "with the shipped default. Your current values will be lost. Export a settings bundle first if you may need them later.": "恢复为默认设置，当前设置将被覆盖。如需保留，请先导出设置包。",
};

const UNCHANGED_ZH_CN_SOURCES = new Set([
  "acme",
  "Acme",
  "America/New_York",
  "Ashby",
  "ATS",
  "BambooHR",
  "Breezy HR",
  "CoderPad",
  "CodeSignal",
  "GitHub",
  "Gmail",
  "Google",
  "Google Meet",
  "Greenhouse",
  "HackerRank",
  "JazzHR",
  "Karat",
  "Lever",
  "Microsoft Teams",
  "n=",
  "OA",
  "Personio",
  "portfolio, flagship-project",
  "Recruitee",
  // The data-reset confirmation must match the literal expected by the API.
  "RESET",
  "Résumé Tailor Harness",
  "SmartRecruiters",
  "wd5",
  "Webex",
  "Workable",
  "Workday",
]);

function isFormattingOnly(value) {
  return /^[\s·•—#%→/…{}v\d–]+$/.test(value);
}

function filesUnder(directory) {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const resolved = path.join(directory, entry.name);
    if (entry.isDirectory()) return filesUnder(resolved);
    if (!/\.(ts|tsx)$/.test(entry.name) || /\.(test|spec)\.(ts|tsx)$/.test(entry.name)) return [];
    if (resolved.includes(`${path.sep}i18n${path.sep}`)) return [];
    return [resolved];
  });
}

function pythonFilesUnder(directory) {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const resolved = path.join(directory, entry.name);
    if (entry.isDirectory()) return pythonFilesUnder(resolved);
    return entry.name.endsWith(".py") ? [resolved] : [];
  });
}

function collect() {
  const found = new Map();
  for (const filename of filesUnder(sourceRoot)) {
    const source = fs.readFileSync(filename, "utf8");
    const ast = parse(source, {
      sourceType: "module",
      plugins: ["typescript", "jsx"],
    });
    traverse(ast, {
      JSXText(pathRef) {
        if (!isLocalizableStringPath(pathRef)) return;
        record(pathRef.node.value, filename, pathRef.node.loc?.start.line);
      },
      StringLiteral(pathRef) {
        if (!isLocalizableStringPath(pathRef)) return;
        record(pathRef.node.value, filename, pathRef.node.loc?.start.line);
      },
      TemplateLiteral(pathRef) {
        if (!isLocalizableStringPath(pathRef)) return;
        record(templateSource(pathRef.node), filename, pathRef.node.loc?.start.line);
      },
    });
  }
  return found;

  function record(value, filename, line) {
    const source = clean(value);
    const locations = found.get(source) ?? [];
    locations.push(`${path.relative(root, filename).replaceAll("\\", "/")}:${line ?? 1}`);
    found.set(source, locations);
  }
}

function collectUnclassified() {
  const found = new Map();
  for (const filename of filesUnder(sourceRoot)) {
    const source = fs.readFileSync(filename, "utf8");
    const ast = parse(source, { sourceType: "module", plugins: ["typescript", "jsx"] });
    traverse(ast, {
      StringLiteral(pathRef) {
        if (isLocalizableStringPath(pathRef) || !isHumanText(pathRef.node.value)) return;
        record(pathRef.node.value, filename, pathRef.node.loc?.start.line);
      },
      TemplateLiteral(pathRef) {
        const value = templateSource(pathRef.node);
        if (isLocalizableStringPath(pathRef) || !isHumanText(value)) return;
        record(value, filename, pathRef.node.loc?.start.line);
      },
    });
  }
  return found;

  function record(value, filename, line) {
    const source = clean(value);
    const locations = found.get(source) ?? [];
    locations.push(`${path.relative(root, filename).replaceAll("\\", "/")}:${line ?? 1}`);
    found.set(source, locations);
  }
}

const candidates = collect();
const catalog = JSON.parse(fs.readFileSync(catalogPath, "utf8"));
const dynamicZhCN = JSON.parse(fs.readFileSync(dynamicZhCNPath, "utf8"));
const missing = [...candidates.entries()].filter(([source]) => !catalog[source]);
const stale = Object.keys(catalog).filter((source) => !candidates.has(source));

function normalizeBackendProgressLabel(label) {
  return label.replace(/\{[^{}]+\}/g, "{{value}}");
}

function reporterCallArguments(source, start) {
  const open = source.indexOf("(", start);
  let depth = 0;
  let quote = null;
  for (let index = open; index < source.length; index += 1) {
    const char = source[index];
    if (quote) {
      if (char === "\\") {
        index += 1;
      } else if (char === quote) {
        quote = null;
      }
      continue;
    }
    if (char === "\"" || char === "'") {
      quote = char;
    } else if (char === "(") {
      depth += 1;
    } else if (char === ")") {
      depth -= 1;
      if (depth === 0) return source.slice(open + 1, index);
    }
  }
  return "";
}

function collectBackendProgressLabels() {
  const labels = new Map();
  for (const filename of pythonFilesUnder(backendSourceRoot)) {
    const source = fs.readFileSync(filename, "utf8");
    for (const call of source.matchAll(/\b\w*reporter\.(?:begin|step)\(/g)) {
      const start = call.index ?? 0;
      const match = /,\s*(?:label\s*=\s*)?(?:f)?(["'])([\s\S]*?)\1/.exec(reporterCallArguments(source, start));
      if (!match) continue;
      const label = normalizeBackendProgressLabel(match[2]);
      const locations = labels.get(label) ?? [];
      const line = source.slice(0, start).split("\n").length;
      locations.push(`${path.relative(root, filename).replaceAll("\\", "/")}:${line}`);
      labels.set(label, locations);
    }
  }
  return labels;
}

const backendProgressLabels = collectBackendProgressLabels();
const missingBackendProgressTranslations = [...backendProgressLabels.entries()]
  .filter(([label]) => typeof dynamicZhCN.runPhases?.[label] !== "string" || !dynamicZhCN.runPhases[label].trim());
const invalidDynamicValues = [
  ["sourceModes", ["literal", "synthesis", "project"]],
  ["sourceFragmentStatuses", ["cached", "extracted", "source-changed", "missing", "stale"]],
  ["runStatuses", ["queued", "cancelling", "succeeded", "failed", "cancelled"]],
  ["fallbacks", ["unknownRun", "working", "operationFailed", "unknownMode", "unknownStatus", "etaUnknown"]],
].flatMap(([section, keys]) => keys.filter((key) => typeof dynamicZhCN[section]?.[key] !== "string" || !dynamicZhCN[section][key].trim())
  .map((key) => `${section}.${key}`));

function stableKey(source) {
  return `ui_${createHash("sha256").update(source).digest("hex").slice(0, 12)}`;
}

function pruneCatalog() {
  const pruned = Object.fromEntries(
    Object.entries(catalog)
      .filter(([source]) => candidates.has(source))
      .sort(([left], [right]) => left.localeCompare(right)),
  );
  fs.writeFileSync(catalogPath, `${JSON.stringify(pruned, null, 2)}\n`);
  console.log(`Pruned catalog to ${Object.keys(pruned).length} current UI entries.`);
}

function applyFixedTranslations() {
  let updated = 0;
  for (const [source, zhCN] of Object.entries(FIXED_ZH_CN_TRANSLATIONS)) {
    if (!candidates.has(source)) continue;
    const entry = catalog[source];
    if (!entry) {
      catalog[source] = { key: stableKey(source), en: source, "zh-CN": zhCN };
      updated += 1;
      continue;
    }
    if (entry["zh-CN"] === zhCN) continue;
    entry["zh-CN"] = zhCN;
    updated += 1;
  }
  const sorted = Object.fromEntries(Object.entries(catalog).sort(([left], [right]) => left.localeCompare(right)));
  fs.writeFileSync(catalogPath, `${JSON.stringify(sorted, null, 2)}\n`);
  console.log(`Applied ${updated} fixed Simplified Chinese translations.`);
}

function validateCatalog() {
  const invalid = [];
  const keys = new Set();
  for (const [source, entry] of Object.entries(catalog)) {
    if (!entry || entry.en !== source || typeof entry["zh-CN"] !== "string" || !entry["zh-CN"].trim()) {
      invalid.push(source);
      continue;
    }
    if (keys.has(entry.key)) invalid.push(source);
    keys.add(entry.key);
    if (FIXED_ZH_CN_TRANSLATIONS[source] && entry["zh-CN"] !== FIXED_ZH_CN_TRANSLATIONS[source]) {
      invalid.push(source);
    }
    if (entry["zh-CN"] === source && !isFormattingOnly(source) && !UNCHANGED_ZH_CN_SOURCES.has(source)) {
      invalid.push(source);
    }
    const sourceVariables = new Set(source.match(/\{\{v\d+\}\}/g) ?? []);
    const translatedVariables = entry["zh-CN"].match(/\{\{v\d+\}\}/g) ?? [];
    if (translatedVariables.some((variable) => !sourceVariables.has(variable))) invalid.push(source);
  }
  return [...new Set(invalid)];
}

function runtimeCatalog(language) {
  return Object.fromEntries(
    Object.values(catalog)
      .map((entry) => [entry.key, entry[language]])
      .sort(([left], [right]) => left.localeCompare(right)),
  );
}

function writeRuntimeCatalogs() {
  for (const [language, filename] of Object.entries(runtimeCatalogPaths)) {
    fs.writeFileSync(
      filename,
      `${JSON.stringify(runtimeCatalog(language), null, 2)}\n`,
    );
  }
  console.log("Generated compact runtime catalogs for en and zh-CN.");
}

function invalidRuntimeCatalogs() {
  return Object.entries(runtimeCatalogPaths).flatMap(([language, filename]) => {
    if (!fs.existsSync(filename)) return [language];
    const actual = JSON.parse(fs.readFileSync(filename, "utf8"));
    return JSON.stringify(actual) === JSON.stringify(runtimeCatalog(language))
      ? []
      : [language];
  });
}

const keyFlagIndex = process.argv.indexOf("--key");

if (process.argv.includes("--apply-fixed")) {
  applyFixedTranslations();
} else if (process.argv.includes("--prune")) {
  pruneCatalog();
} else if (process.argv.includes("--write-runtime")) {
  writeRuntimeCatalogs();
} else if (process.argv.includes("--unclassified")) {
  const unclassified = collectUnclassified();
  process.stdout.write(`${JSON.stringify(Object.fromEntries(unclassified), null, 2)}\n`);
} else if (keyFlagIndex !== -1) {
  const source = process.argv[keyFlagIndex + 1];
  if (!source) {
    console.error("Usage: node scripts/i18n-catalog.mjs --key \"<source text>\"");
    process.exitCode = 1;
  } else {
    console.log(stableKey(source));
  }
} else if (process.argv.includes("--json")) {
  process.stdout.write(`${JSON.stringify(Object.fromEntries(candidates), null, 2)}\n`);
} else {
  const invalid = validateCatalog();
  const invalidRuntime = invalidRuntimeCatalogs();
  if (missing.length) {
    console.error(`Missing ${missing.length} UI translations. Every entry is a fixed, hand-written`);
    console.error(`translation — there is no machine-translation fallback. For each string below,`);
    console.error(`run \`node scripts/i18n-catalog.mjs --key "<source text>"\` to get its key, then`);
    console.error(`add { "key": "...", "en": "<source text>", "zh-CN": "<hand-written translation>" }`);
    console.error(`to src/i18n/auto-catalog.json:`);
    for (const [source, locations] of missing) {
      console.error(`- ${JSON.stringify(source)} (${locations.slice(0, 3).join(", ")})`);
    }
  }
  if (stale.length) {
    console.error(`Catalog contains ${stale.length} unused entries:`);
    for (const source of stale) console.error(`- ${JSON.stringify(source)}`);
  }
  if (invalid.length) {
    console.error(`Catalog contains ${invalid.length} invalid entries:`);
    for (const source of invalid) console.error(`- ${JSON.stringify(source)}`);
  }
  if (invalidRuntime.length) {
    console.error(
      `Runtime catalogs are missing or stale for: ${invalidRuntime.join(", ")}.`,
    );
    console.error("Run `npm run i18n:generate` and commit the generated files.");
  }
  if (missingBackendProgressTranslations.length) {
    console.error(`Missing ${missingBackendProgressTranslations.length} Chinese backend progress labels:`);
    for (const [label, locations] of missingBackendProgressTranslations) {
      console.error(`- ${JSON.stringify(label)} (${locations.slice(0, 3).join(", ")})`);
    }
  }
  if (invalidDynamicValues.length) {
    console.error(`Dynamic Chinese labels are missing or invalid: ${invalidDynamicValues.join(", ")}`);
  }
  if (!missing.length && !stale.length && !invalid.length && !invalidRuntime.length
      && !missingBackendProgressTranslations.length && !invalidDynamicValues.length) {
    console.log(`i18n catalog covers ${candidates.size} user-facing literals and ${backendProgressLabels.size} backend progress labels.`);
  }
  process.exitCode = missing.length || stale.length || invalid.length || invalidRuntime.length
    || missingBackendProgressTranslations.length || invalidDynamicValues.length ? 1 : 0;
}
