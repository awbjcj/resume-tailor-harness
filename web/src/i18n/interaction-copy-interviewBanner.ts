import i18n from "i18next";

export const interviewBannerCopyEn = {
  active: "Mock interview in progress",
  activeCount_one: "{{count}} mock interview in progress",
  activeCount_other: "{{count}} mock interviews in progress",
  resume: "Resume",
  open: "Open interviews",
};

function register() {
  i18n.addResourceBundle("en", "translation", { interactionCopy: { interviewBanner: interviewBannerCopyEn } }, true, true);
}

if (i18n.isInitialized) register();
else i18n.on("initialized", register);
