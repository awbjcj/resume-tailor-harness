import i18n from "./index";

export const decisionsEn = {
  title: "Fast skill classification",
  description: "Use OpenAI Decisions to group profile skills, assign categories, and select existing domains.",
  enrollment: "Enable direct OpenAI Decisions",
  billing: "Enabling this feature sends skill names and relevant context directly to OpenAI and charges the API balance associated with the key below. It bypasses Sub2API, even when OpenAI normally uses your subscription gateway. Shared spending limits still apply.",
  quality: "Clear classifications use the fast path. Uncertain results, new domains, and provider failures fall back to your usual models and routing. Manual corrections are preserved. Speed and cost depend on how many skills need fallback.",
  key: "Direct OpenAI API key",
  configured: "Key saved — leave blank to keep it",
  placeholder: "Paste an OpenAI API key",
  keyHelp: "Stored separately from gateway and personal keys. The saved key is never returned to your browser.",
  clear: "Remove Decisions key",
  cleared: "The key will be removed and the feature disabled when you save.",
  save: "Save classification settings",
  saving: "Saving…",
  saved: "Classification settings saved. Changes apply to new operations.",
  discard: "Discard edits",
  loading: "Loading classification settings…",
  loadError: "Classification settings could not load.",
  saveError: "Could not save. Check the direct API key and try again.",
  retry: "Retry",
  missingKey: "Add an OpenAI API key before enabling this feature.",
  route: "Direct route: api.openai.com · gpt-6-luna",
};

export const decisionsZh: typeof decisionsEn = {
  title: "快速技能分类",
  description: "使用 OpenAI Decisions 为个人技能分组、分配类别并选择已有领域。",
  enrollment: "启用 OpenAI Decisions 直连",
  billing: "启用后，技能名称和相关上下文将直接发送至 OpenAI，并使用下方密钥所属账户的 API 余额计费。即使 OpenAI 通常通过订阅网关访问，此功能也会绕过 Sub2API。平台共享用量限额仍然有效。",
  quality: "分类结果明确时使用快速通道；结果不确定、涉及新领域或服务商出错时，会回退到原有模型和路由。手动修正会保留。实际速度和费用取决于需要回退处理的技能数量。",
  key: "OpenAI 直连 API 密钥",
  configured: "已保存密钥，留空即可保留",
  placeholder: "粘贴 OpenAI API 密钥",
  keyHelp: "此密钥与网关密钥及个人密钥分开保存，保存后不会返回浏览器。",
  clear: "移除 Decisions 密钥",
  cleared: "保存后将移除密钥并停用此功能。",
  save: "保存分类设置",
  saving: "正在保存…",
  saved: "分类设置已保存，将对新启动的操作生效。",
  discard: "放弃修改",
  loading: "正在加载分类设置…",
  loadError: "无法加载分类设置。",
  saveError: "保存失败，请检查直连 API 密钥后重试。",
  retry: "重试",
  missingKey: "请先添加 OpenAI API 密钥，再启用此功能。",
  route: "直连地址：api.openai.com · gpt-6-luna",
};

function register() {
  i18n.addResourceBundle("en", "translation", { decisions: decisionsEn }, true, true);
  i18n.addResourceBundle("zh-CN", "translation", { decisions: decisionsZh }, true, true);
}
if (i18n.isInitialized) register();
else i18n.on("initialized", register);
