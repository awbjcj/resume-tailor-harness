import i18n from "i18next";

export const providerSetupEn = {
  title: "Choose an AI provider",
  description: "This provider will power your profile and résumé workflows. You can adjust model tiers later in Settings.",
  provider: "AI provider",
  apiFormat: "API format",
  keepCurrent: "Keep current model tiers",
  custom: "Use a custom API endpoint",
  baseUrl: "API base URL",
  baseUrlHelp: {
    openai: "Use the base URL for an OpenAI Responses-compatible API, including its path, such as /v1.",
    anthropic: "Use the base URL for an Anthropic Messages-compatible API.",
    gemini: "Use the base URL for a Gemini GenerateContent-compatible API.",
    deepseek: "Use the base URL for a DeepSeek Responses-compatible API, including its path, such as /v1.",
  },
  modelId: "Model ID",
  modelHelp: "Enter the model ID exactly as it appears in your provider's documentation.",
  apiKey: "API key",
  optionalKey: "API key (optional)",
  savedEndpointKey: "Leave blank to keep the saved key for this endpoint.",
  availableKey: "This provider is already available to your workspace.",
  showKey: "Show API key",
  hideKey: "Hide API key",
  save: "Save & continue",
  saving: "Saving…",
  continue: "Continue",
  skip: "Skip for now",
  optionalCredentials: "Other service credentials",
  retry: "Retry",
  loading: "Loading providers…",
  loadError: "Couldn’t load providers. Try again to continue setup.",
  saveError: "Couldn’t save the provider. Try again.",
  invalidProvider: "Choose a supported provider.",
  unavailable: "This provider is unavailable. Choose another provider.",
  invalidUrl: "Enter an HTTP or HTTPS API base URL without credentials, a query, or a fragment.",
  invalidModel: "Enter the exact model ID from your provider.",
  requiredKey: "Enter the API key for this connection.",
  invalidKey: "Paste the API key exactly as your provider issued it, without spaces or non-ASCII characters.",
};

const zh: typeof providerSetupEn = {
  title: "选择 AI 服务商",
  description: "此服务商将用于构建个人资料和处理简历。之后可以在设置中调整模型档位。",
  provider: "AI 服务商",
  apiFormat: "API 格式",
  keepCurrent: "保留当前模型档位",
  custom: "使用自定义 API 端点",
  baseUrl: "API 基础网址",
  baseUrlHelp: {
    openai: "输入兼容 OpenAI Responses API 的基础网址，包含 /v1 等接口路径。",
    anthropic: "输入兼容 Anthropic Messages API 的基础网址。",
    gemini: "输入兼容 Gemini GenerateContent API 的基础网址。",
    deepseek: "输入兼容 DeepSeek Responses API 的基础网址，包含 /v1 等接口路径。",
  },
  modelId: "模型 ID",
  modelHelp: "请按服务商文档中的原样输入模型 ID。",
  apiKey: "API 密钥",
  optionalKey: "API 密钥（选填）",
  savedEndpointKey: "留空即可保留此端点已保存的密钥。",
  availableKey: "此服务商已可在当前工作区使用。",
  showKey: "显示 API 密钥",
  hideKey: "隐藏 API 密钥",
  save: "保存并继续",
  saving: "正在保存…",
  continue: "继续",
  skip: "暂时跳过",
  optionalCredentials: "其他服务凭据",
  retry: "重试",
  loading: "正在加载服务商…",
  loadError: "无法加载服务商，请重试以继续设置。",
  saveError: "无法保存服务商设置，请重试。",
  invalidProvider: "请选择受支持的服务商。",
  unavailable: "此服务商暂不可用，请选择其他服务商。",
  invalidUrl: "请输入 HTTP 或 HTTPS 基础网址，网址中不可包含登录凭据、查询参数或片段。",
  invalidModel: "请输入服务商提供的准确模型 ID。",
  requiredKey: "请输入用于此连接的 API 密钥。",
  invalidKey: "请粘贴服务商提供的原始 API 密钥，去掉空格和非 ASCII 字符。",
};

function register() {
  i18n.addResourceBundle("en", "translation", { providerSetup: providerSetupEn }, true, true);
  i18n.addResourceBundle("zh-CN", "translation", { providerSetup: zh }, true, true);
}

if (i18n.isInitialized) register();
else i18n.on("initialized", register);
