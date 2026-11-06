import i18n from "i18next";

export const redoCopyEn = {
  jobCount_one: "{{count}} job",
  jobCount_other: "{{count}} jobs",
  button: "Redo {{jobs}}",
  cleanupButton: "Redo and delete older versions",
  description: "Choose which stages to rerun for {{jobs}}. Existing resume versions are kept by default.",
  renderNew: "Create a PDF from the final resume in this run.",
  removePrevious: "Delete older generated versions",
  removePreviousHint: "Once the new resume passes fact-lock, Redo permanently deletes unused versions from earlier tailoring runs. It keeps versions selected for an application or linked to a revision or cover letter. To delete older versions with a PDF, select Re-render PDF so the new PDF is ready first.",
};

function register() {
  i18n.addResourceBundle("en", "translation", { interactionCopy: { redo: redoCopyEn } }, true, true);
}

if (i18n.isInitialized) register();
else i18n.on("initialized", register);
