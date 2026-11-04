import i18n from "i18next";

export const redoCopyEn = {
  jobCount_one: "{{count}} job",
  jobCount_other: "{{count}} jobs",
  button: "{{stages}} {{jobs}}",
  description: "Re-run any stage on {{jobs}}, whatever their status. Existing resume versions and PDFs are kept.",
  pull: "Re-pull",
  extract: "Re-extract",
  tailor: "Re-tailor",
  render: "Re-render",
};

function register() {
  i18n.addResourceBundle("en", "translation", { interactionCopy: { redo: redoCopyEn } }, true, true);
}

if (i18n.isInitialized) register();
else i18n.on("initialized", register);
