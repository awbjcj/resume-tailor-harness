import i18n from "i18next";

export const sourcesCopyEn = {
  pullSelected: "Pull selected ({{count}})",
  added: "+{{count}} added",
  updated: "{{count}} upgraded",
  skipped: "{{count}} skipped",
};

function register() {
  i18n.addResourceBundle("en", "translation", { interactionCopy: { sources: sourcesCopyEn } }, true, true);
}

if (i18n.isInitialized) register();
else i18n.on("initialized", register);
