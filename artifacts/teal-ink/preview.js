(() => {
  "use strict";
  const root = document.documentElement;
  const themeChoice = document.querySelector("#theme-choice");
  const languageToggle = document.querySelector("#language-toggle");
  const search = document.querySelector("#token-search");
  const layer = document.querySelector("#token-layer");
  const status = document.querySelector("#preview-status");
  const dialog = document.querySelector("#review-dialog");
  const media = window.matchMedia("(prefers-color-scheme: dark)");
  const english = new Map();
  const translatedAttributes = [["data-i18n", "textContent"], ["data-i18n-aria", "aria-label"], ["data-i18n-placeholder", "placeholder"]];
  for (const [attribute, property] of translatedAttributes) {
    document.querySelectorAll(`[${attribute}]`).forEach((element) => {
      english.set(element.getAttribute(attribute), property === "textContent" ? element.textContent : element.getAttribute(property));
    });
  }
  const zh = {
    skip: "跳至主要内容", brandSub: "可复用的设计语言", library: "设计资源", navLabel: "设计系统导航", overview: "概览", foundations: "基础规范", components: "组件", patterns: "组合模式", tokens: "设计令牌", adopt: "应用到新项目", offline: "完全离线可用", designSystem: "设计系统", preview: "交互参考", theme: "主题", light: "浅色", dark: "深色", system: "跟随系统",
    heroEyebrow: "从一个工作空间，延续到下一个", heroLead: "界面从容，决策清晰。", heroCopy: "从 Résumé Tailor 提炼的视觉语言，整理成可带入下一个项目的设计系统。", explore: "查看组件", readGuide: "阅读指南", liveSpecimen: "实时组件示例", workspace: "你的工作空间", sampleTitle: "让下一步更清晰。", sampleCopy: "把下一步需要的信息和操作放在一起，方便查看与确认。", readyReview: "待审核内容", progressLabel: "示例审核进度", verified: "已验证", needsReview: "待审核", sampleData: "示例内容", review: "审核更改", specimenCaption: "同一组组件，适配不同主题。", themesLabel: "主题", architectureLabel: "结构", architectureValue: "三层设计令牌", coreLabel: "核心", coreValue: "纯 CSS · 无运行时依赖", themesValue: "浅色 / 深色 / 登录入口",
    foundationsTitle: "克制，也有自己的风格。", foundationsCopy: "青色引导操作，墨色构建层次。每一种颜色都有用途。", typography: "字体与排版", typeSample: "把下一步说清楚。", typeDescription: "15px 正文、克制的标题、等宽排列的数字。中文使用系统字体回退，保证可读性。", rhythm: "间距与形状", rhythmMeta: "以 4px 为基础", shapeCopy: "8px 基础圆角、轻盈的双层阴影，以及自然换行的内容。", principle1: "先有结构，再做装饰", principle1Copy: "用分隔线、整齐的行与一致的间距，减轻密集信息的阅读负担。", principle2: "让下一步清楚可见", principle2Copy: "把实心青色按钮留给推动当前任务的主要操作。", principle3: "保留依据与状态", principle3Copy: "明确区分建议、待审核、已批准和已完成。",
    componentsTitle: "组件小巧，组合实用。", componentsCopy: "保留原生交互、清晰的焦点，以及真实内容需要的空间。", actions: "操作按钮", primaryAction: "主要操作", loadingDemo: "查看加载状态", secondaryAction: "浏览令牌", ghostAction: "预览", dangerAction: "重置示例", disabled: "不可用", actionHint: "用 Tab 键查看焦点效果。触屏操作区域会增至 44px。", formTitle: "字段也能说明白", formCopy: "标签、提示和错误信息始终相连。", projectName: "项目名称", projectHint: "使用团队容易识别的名称。", projectType: "工作空间类型", productWorkspace: "产品工作空间", personalTool: "个人工具", internalDashboard: "内部仪表盘", keepReview: "保留明确的审核步骤", saveExample: "保存示例", localDemo: "仅为预览 · 保留在当前页面", feedback: "让反馈有明确含义", blocked: "已阻止", suggestion: "建议", approvalTitle: "先征得你的批准。", approvalCopy: "确认之前，先展示将修改什么，以及修改会应用到哪里。", errorFieldLabel: "校验状态示例", errorFieldCopy: "请输入项目名称后继续。", loadingPreview: "加载占位", feedbackHint: "颜色需要配合文字或符号。装饰性边框不单独承担状态含义。",
    patternsTitle: "围绕实际工作组织界面。", patternsCopy: "紧凑的行布局让长短不一的内容也能整齐排列。不同宽度下，细节依然清楚。", workspaceTitle: "项目工作空间", workspaceCopy: "可复用的信息、进度与决策界面。", sourcesLabel: "信息来源", verifiedLabel: "已验证条目", pendingLabel: "待审核", frontend: "界面能力", workflow: "工作流程", stage1: "已收集", stage2: "已选择", stage3: "已批准", stage4: "进行中", stage5: "已就绪", longContent: "较长内容", longExample: "这个项目标签包含较多说明，在窄屏上也能自然换行，不会被截断", metricsNote: "预览中的数据和内容均为示例。", gatewayLabel: "登录入口预设", gatewayTitle: "从入口开始，保持专注。", gatewayCopy: "薄荷青与深墨色、安静的流程图、一个专注的表单。延续登录页的氛围，同时保留工作区自己的层次。", gatewayAction: "查看审核模式", gatewayDiagram: "收集 → 审核 → 继续", responsiveChip: "响应式布局", keyboardChip: "键盘导航", localizationChip: "本地化", tokensChip: "设计令牌", themesChip: "主题支持",
    tokensTitle: "每个设计决定，都有名字。", tokensCopy: "基础值 → 语义 → 组件。搜索令牌、查看引用，再复制 CSS 变量。", searchTokens: "搜索令牌", searchPlaceholder: "试试 primary、radius、button…", layer: "层级", allLayers: "全部层级", semanticLayer: "语义层", componentLayer: "组件层", primitiveLayer: "基础层", tokenTableLabel: "设计令牌列表", tokenName: "令牌 / CSS 变量", resolvedValue: "解析后的值", references: "引用", copy: "复制", noTokens: "没有匹配的令牌", noTokensCopy: "试试更短的名称，或选择其他层级。", adoptTitle: "复制、调整，延续这个风格。", adoptCopy: "可以使用整套资源，也可以只把令牌引入现有组件。", quickStart: "从这里开始", copyCode: "复制代码", quickStartCode: "快速开始代码", takeAlong: "可以一起带走的资源", deliverable1: "可编辑的类型化令牌 JSON 与生成的 CSS", deliverable2: "纯 CSS 组件与组合模式", deliverable3: "React 19 源码与 Tailwind v4 适配层", deliverable4: "无障碍、迁移与重构指南", deliverable5: "供下一个编程助手使用的设计说明", readme: "使用说明", migrationGuide: "接入指南", agentBrief: "助手设计说明", footer: "提炼自 Résumé Tailor，供后续项目继续演进。",
    reviewEyebrow: "审核模式 · 示例", reviewTitle: "应用之前，先看清更改。", reviewDescription: "审核弹窗应说明拟议更改、应用位置，以及确认之后会发生什么。", reviewChange: "拟议更改", reviewChangeCopy: "将 Teal & Ink 的外观应用到此预览。此示例不会发送或发布任何内容。", cancel: "取消", confirmExample: "确认示例",
  };
  const dynamic = {
    en: { copied: "Copied", copyFailed: "Copy unavailable. Select the variable or code and copy it manually.", loading: "Working…", loaded: "Loading example complete.", reset: "Example reset.", saved: "Example saved in this page.", required: "Enter a project name to continue.", confirmed: "Example confirmed. No content was sent or published.", variable: "Copy", colorPrimary: "Action teal", colorBackground: "Canvas", colorCard: "Surface", colorForeground: "Ink", colorMuted: "Secondary text", count: (shown, total) => `Showing ${shown} of ${total} matching tokens. Values follow the selected theme.`, toLanguage: "Switch to Simplified Chinese", emptyRef: "Raw value" },
    zh: { copied: "已复制", copyFailed: "暂时无法复制。请选择变量或代码后手动复制。", loading: "处理中…", loaded: "加载状态示例已完成。", reset: "示例已重置。", saved: "示例已保留在当前页面。", required: "请输入项目名称后继续。", confirmed: "已确认示例，没有发送或发布内容。", variable: "复制", colorPrimary: "操作青色", colorBackground: "画布", colorCard: "内容表面", colorForeground: "正文墨色", colorMuted: "次要文字", count: (shown, total) => `当前显示 ${shown} 个，共 ${total} 个匹配令牌。数值随所选主题变化。`, toLanguage: "Switch to English", emptyRef: "基础值" },
  };
  let language = "en";
  let statusTimer;
  let loadingTimer;
  let loading = false;

  function effectiveTheme() {
    const choice = root.dataset.tiTheme;
    return choice === "system" ? (media.matches ? "dark" : "light") : choice;
  }
  function notify(message) {
    clearTimeout(statusTimer);
    status.textContent = message;
    statusTimer = setTimeout(() => { status.textContent = ""; }, 5000);
  }
  async function copy(value) {
    try {
      if (!navigator.clipboard?.writeText) throw new Error("Clipboard unavailable");
      await navigator.clipboard.writeText(value);
    } catch {
      const previouslyFocused = document.activeElement;
      const textarea = document.createElement("textarea");
      textarea.value = value;
      textarea.className = "ti-sr-only";
      textarea.setAttribute("aria-label", "Copy buffer");
      document.body.append(textarea);
      textarea.select();
      let copied = false;
      try { copied = document.execCommand("copy"); } catch { /* Explain manual fallback below. */ }
      textarea.remove();
      previouslyFocused?.focus();
      if (!copied) { notify(dynamic[language].copyFailed); return; }
    }
    notify(`${dynamic[language].copied}: ${value.length > 90 ? "✓" : value}`);
  }
  function renderPalette() {
    const palette = document.querySelector("#palette");
    const catalog = window.TEAL_INK_TOKENS[effectiveTheme()];
    const keys = [["primary", "colorPrimary"], ["background", "colorBackground"], ["card", "colorCard"], ["foreground", "colorForeground"], ["muted-foreground", "colorMuted"]];
    palette.replaceChildren(...keys.map(([key, label]) => {
      const token = catalog.find((entry) => entry.path === `semantic.color.${key}`);
      const button = document.createElement("button");
      button.className = "preview-swatch";
      button.type = "button";
      button.setAttribute("aria-label", `${dynamic[language].variable} ${token.css}`);
      const color = document.createElement("span");
      color.className = "preview-swatch-color";
      color.style.setProperty("--swatch", token.value);
      color.setAttribute("aria-hidden", "true");
      const text = document.createElement("span");
      text.className = "preview-swatch-text";
      const title = document.createElement("strong");
      title.textContent = dynamic[language][label];
      const value = document.createElement("span");
      value.className = "preview-swatch-value";
      value.textContent = token.value.toUpperCase();
      text.append(title, value);
      button.append(color, text);
      button.addEventListener("click", () => copy(`var(${token.css})`));
      return button;
    }));
  }
  function renderTokens() {
    const query = search.value.toLowerCase().trim();
    const catalog = window.TEAL_INK_TOKENS[effectiveTheme()];
    const results = catalog.filter((token) => (layer.value === "all" || token.path.startsWith(`${layer.value}.`)) && `${token.path} ${token.css} ${token.value} ${token.alias ?? ""}`.toLowerCase().includes(query));
    const visible = results.slice(0, 75);
    document.querySelector("#token-count").textContent = dynamic[language].count(visible.length, results.length);
    document.querySelector("#token-empty").hidden = results.length !== 0;
    document.querySelector("#token-results").replaceChildren(...visible.map((token) => {
      const row = document.createElement("tr");
      const name = document.createElement("td");
      const path = document.createElement("span");
      path.className = "preview-token-path";
      path.textContent = token.path;
      const css = document.createElement("code");
      css.textContent = token.css;
      name.append(path, css);
      const valueCell = document.createElement("td");
      if (token.type === "color") {
        const swatch = document.createElement("span");
        swatch.className = "preview-token-color";
        swatch.style.setProperty("--swatch", token.value);
        swatch.setAttribute("aria-hidden", "true");
        valueCell.append(swatch);
      }
      const value = document.createElement("code");
      value.textContent = token.value;
      valueCell.append(value);
      const reference = document.createElement("td");
      reference.className = "ti-muted";
      reference.textContent = token.alias ?? dynamic[language].emptyRef;
      const action = document.createElement("td");
      const button = document.createElement("button");
      button.type = "button";
      button.className = "ti-button";
      button.dataset.variant = "outline";
      button.dataset.size = "sm";
      button.textContent = dynamic[language].variable;
      button.setAttribute("aria-label", `${dynamic[language].variable} ${token.css}`);
      button.addEventListener("click", () => copy(`var(${token.css})`));
      action.append(button);
      row.append(name, valueCell, reference, action);
      return row;
    }));
  }
  function renderLoading() {
    const button = document.querySelector("#load-demo");
    button.disabled = loading;
    button.setAttribute("aria-busy", String(loading));
    button.textContent = loading ? dynamic[language].loading : (language === "zh" ? zh.loadingDemo : english.get("loadingDemo"));
  }
  function setLanguage(next) {
    language = next;
    root.lang = next === "zh" ? "zh-CN" : "en";
    for (const [attribute, property] of translatedAttributes) {
      document.querySelectorAll(`[${attribute}]`).forEach((element) => {
        const key = element.getAttribute(attribute);
        const text = next === "zh" ? zh[key] : english.get(key);
        if (text === undefined) throw new Error(`Missing translation: ${key}`);
        if (property === "textContent") element.textContent = text;
        else element.setAttribute(property, text);
      });
    }
    languageToggle.textContent = next === "zh" ? "EN" : "中文";
    languageToggle.setAttribute("aria-label", dynamic[next].toLanguage);
    if (!document.querySelector("#project-error").hidden) document.querySelector("#project-error").textContent = dynamic[next].required;
    status.textContent = "";
    renderLoading();
    renderPalette();
    renderTokens();
    try { localStorage.setItem("teal-ink-preview-language", next); } catch { /* Optional persistence. */ }
  }
  function updateTheme() {
    root.dataset.tiTheme = themeChoice.value;
    renderPalette();
    renderTokens();
    try { localStorage.setItem("teal-ink-preview-theme", themeChoice.value); } catch { /* Optional persistence. */ }
  }
  themeChoice.value = root.dataset.tiTheme;
  themeChoice.addEventListener("change", updateTheme);
  media.addEventListener("change", () => { if (themeChoice.value === "system") { renderPalette(); renderTokens(); } });
  languageToggle.addEventListener("click", () => setLanguage(language === "en" ? "zh" : "en"));
  search.addEventListener("input", renderTokens);
  layer.addEventListener("change", renderTokens);
  document.querySelectorAll("[data-open-review]").forEach((button) => button.addEventListener("click", () => { dialog.returnValue = ""; dialog.showModal(); }));
  dialog.addEventListener("close", () => { if (dialog.returnValue === "confirm") notify(dynamic[language].confirmed); });
  document.querySelector("#load-demo").addEventListener("click", () => {
    loading = true;
    renderLoading();
    loadingTimer = setTimeout(() => { loading = false; renderLoading(); notify(dynamic[language].loaded); }, 900);
  });
  document.querySelector("#example-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const input = document.querySelector("#project-name");
    const error = document.querySelector("#project-error");
    const invalid = !input.value.trim();
    input.setAttribute("aria-invalid", String(invalid));
    error.hidden = !invalid;
    error.textContent = invalid ? dynamic[language].required : "";
    if (invalid) input.focus();
    else notify(dynamic[language].saved);
  });
  document.querySelector("#danger-demo").addEventListener("click", () => {
    clearTimeout(loadingTimer);
    loading = false;
    renderLoading();
    document.querySelector("#example-form").reset();
    document.querySelector("#project-error").hidden = true;
    document.querySelector("#project-name").removeAttribute("aria-invalid");
    notify(dynamic[language].reset);
  });
  document.querySelector("#copy-quickstart").addEventListener("click", () => copy(document.querySelector("#quickstart-code").textContent));
  const navLinks = [...document.querySelectorAll(".preview-nav a")];
  const observer = new IntersectionObserver((entries) => {
    for (const entry of entries) if (entry.isIntersecting) {
      for (const link of navLinks) {
        if (link.hash === `#${entry.target.id}`) link.setAttribute("aria-current", "location");
        else link.removeAttribute("aria-current");
      }
    }
  }, { rootMargin: "-10% 0px -65% 0px", threshold: 0 });
  document.querySelectorAll(".preview-section").forEach((section) => observer.observe(section));
  let savedLanguage = "en";
  try { if (localStorage.getItem("teal-ink-preview-language") === "zh") savedLanguage = "zh"; } catch { /* Offline file mode is supported. */ }
  setLanguage(savedLanguage);
})();
