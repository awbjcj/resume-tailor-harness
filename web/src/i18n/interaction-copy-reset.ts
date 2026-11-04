import i18n from "i18next";

export const resetCopyEn = {
  title: "Reset {{scope}}?",
  description: "The selected data will be permanently deleted. {{description}} Type RESET to continue.",
  replace: "Replace {{title}}?",
};

function register() {
  i18n.addResourceBundle("en", "translation", { interactionCopy: { reset: resetCopyEn } }, true, true);
}

if (i18n.isInitialized) register();
else i18n.on("initialized", register);
