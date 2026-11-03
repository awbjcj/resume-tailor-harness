import i18n from "i18next";

export const workflowEn = {
  profileReady: "Your profile is ready for tailoring.",
  dashboard: "Go to dashboard", returnToTask: "Return to your task", nextStep: "Next step",
  setup: "Continue setup", running: "Work is in progress", openResult: "Open result", openResults: "Open results",
  unavailable: "The original result is no longer available. Open the workspace to continue.",
  next: { triage: "Review job", approve: "Approve for tailoring", tailor: "Tailor resume", review: "Review resume", render: "Render PDF", apply: "Prepare application", track: "View application history" },
  hint: { triage: "Review the posting and decide whether to keep it.", approve: "Approve this job before creating tailored materials.", tailor: "Create a resume from your saved facts.", review: "Resolve any issues from the checks on your chosen resume before using it.", render: "Create a PDF of the resume you plan to use.", apply: "Your resume PDF is available. Use your selected materials to complete the application.", track: "Your submission or an update from the employer has been recorded. Continue in your application history." },
  prepare: "Prepare your application", renderTask: "Render a resume", applyTask: "Prepare and record submission",
  renderHint: "Review the resume and create its PDF.", applyHint: "Prepare the application, then record submission only after it is confirmed.",
};

export const workflowZh = {
  profileReady: "个人资料已就绪，可用于定制简历。",
  dashboard: "前往概览", returnToTask: "返回原来的任务", nextStep: "下一步",
  setup: "继续设置", running: "任务正在进行", openResult: "打开结果", openResults: "查看结果",
  unavailable: "原来的结果已不可用。请打开工作区继续。",
  next: { triage: "查看职位", approve: "批准并准备定制", tailor: "定制简历", review: "检查简历", render: "生成 PDF", apply: "准备职位申请", track: "查看申请记录" },
  hint: { triage: "查看职位信息，决定是否保留。", approve: "先批准这个职位，再生成定制材料。", tailor: "根据已保存的事实创建简历。", review: "解决所选简历的核验问题后再使用。", render: "为即将使用的简历生成 PDF。", apply: "简历 PDF 已就绪。使用所选材料完成申请。", track: "已记录投递或雇主的进展。可前往申请记录继续跟进。" },
  prepare: "准备职位申请", renderTask: "生成简历 PDF", applyTask: "准备申请并记录投递",
  renderHint: "检查简历并生成 PDF。", applyHint: "准备职位申请，确认已投递后再记录。",
};

function register() {
  i18n.addResourceBundle("en", "translation", { workflow: workflowEn }, true, true);
  i18n.addResourceBundle("zh-CN", "translation", { workflow: workflowZh }, true, true);
}

if (i18n.isInitialized) register();
else i18n.on("initialized", register);
