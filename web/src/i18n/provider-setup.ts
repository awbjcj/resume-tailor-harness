import i18n from "i18next";

export const providerSetupEn = {
  title: "Choose an AI provider",
  description: "This provider handles profile and resume tasks. You can change model tiers later in Settings.",
  provider: "AI provider",
  apiFormat: "API format",
  keepCurrent: "Keep current model tiers",
  custom: "Use a custom API endpoint",
  baseUrl: "API base URL",
  baseUrlHelp: {
    openai: "Enter the base URL for an endpoint that supports OpenAI Responses. Include its API path, such as /v1.",
    anthropic: "Enter the base URL for an endpoint that supports Anthropic Messages.",
    gemini: "Enter the base URL for an endpoint that supports Gemini GenerateContent.",
    deepseek: "Enter the base URL for an endpoint that supports DeepSeek Responses. Include its API path, such as /v1.",
  },
  modelId: "Model ID",
  modelHelp: "Copy the exact model ID from your provider's documentation.",
  apiKey: "API key",
  optionalKey: "API key (optional)",
  savedEndpointKey: "Leave this blank to keep the saved key for this endpoint.",
  availableKey: "Your workspace can already use this provider.",
  showKey: "Show API key",
  hideKey: "Hide API key",
  save: "Save & continue",
  saving: "Saving…",
  continue: "Continue",
  skip: "Skip for now",
  optionalCredentials: "Other service credentials",
  retry: "Retry",
  loading: "Loading providers…",
  loadError: "Couldn't load the provider list. Try again.",
  saveError: "Couldn’t save the provider. Try again.",
  invalidProvider: "Choose a supported provider.",
  unavailable: "This provider is unavailable. Choose another provider.",
  invalidUrl: "Enter an HTTP or HTTPS API base URL without credentials, a query, or a fragment.",
  invalidModel: "Enter the exact model ID from your provider.",
  requiredKey: "Enter an API key for this connection.",
  invalidKey: "Paste the key from your provider. Use printable ASCII characters without spaces.",
  customUnavailable: "Custom API endpoints are available in local workspaces only.",
};

const zh: typeof providerSetupEn = {
  title: "选择 AI 服务商",
  description: "构建个人资料和处理简历时会使用此服务商。之后可在设置中调整模型档位。",
  provider: "AI 服务商",
  apiFormat: "API 格式",
  keepCurrent: "保留当前模型档位",
  custom: "使用自定义 API 端点",
  baseUrl: "API 基础网址",
  baseUrlHelp: {
    openai: "填写支持 OpenAI Responses API 的基础网址，包含 /v1 这样的接口路径。",
    anthropic: "填写支持 Anthropic Messages API 的基础网址。",
    gemini: "填写支持 Gemini GenerateContent API 的基础网址。",
    deepseek: "填写支持 DeepSeek Responses API 的基础网址，包含 /v1 这样的接口路径。",
  },
  modelId: "模型 ID",
  modelHelp: "请按服务商文档原样填写模型 ID。",
  apiKey: "API 密钥",
  optionalKey: "API 密钥（选填）",
  savedEndpointKey: "留空会继续使用为此端点保存的密钥。",
  availableKey: "当前工作区已可使用此服务商。",
  showKey: "显示 API 密钥",
  hideKey: "隐藏 API 密钥",
  save: "保存并继续",
  saving: "正在保存…",
  continue: "继续",
  skip: "暂时跳过",
  optionalCredentials: "其他服务的凭据",
  retry: "重试",
  loading: "正在加载服务商…",
  loadError: "无法加载服务商列表，请重试。",
  saveError: "无法保存服务商设置，请重试。",
  invalidProvider: "请选择受支持的服务商。",
  unavailable: "此服务商暂不可用，请选择其他服务商。",
  invalidUrl: "请输入 HTTP 或 HTTPS 基础网址，网址中不可包含登录凭据、查询参数或片段。",
  invalidModel: "请输入服务商提供的准确模型 ID。",
  requiredKey: "请输入用于此连接的 API 密钥。",
  invalidKey: "请粘贴服务商提供的密钥。密钥只能包含可打印的 ASCII 字符，且不能有空格。",
  customUnavailable: "只有本地工作区支持自定义 API 端点。",
};

function register() {
  i18n.addResourceBundle("en", "translation", { providerSetup: providerSetupEn }, true, true);
  i18n.addResourceBundle("zh-CN", "translation", { providerSetup: zh }, true, true);
}

if (i18n.isInitialized) register();
else i18n.on("initialized", register);
