import i18n from "i18next";

export const redoCopyEn = {
  jobCount_one: "{{count}} job",
  jobCount_other: "{{count}} jobs",
  button: "Redo {{jobs}}",
  cleanupButton: "Redo and remove versions",
  description: "Re-run stages for {{jobs}}. Existing resume versions are kept by default.",
  renderNew: "Render the final resume from this run.",
  removePrevious: "Remove superseded generated versions",
  removePreviousHint: "After the new resume passes fact-lock, permanently delete unused generated versions. Application selections and versions linked to revisions or cover letters are kept. Include Re-render PDF to remove older rendered versions once the new PDF is ready.",
};

function register() {
  i18n.addResourceBundle("en", "translation", { interactionCopy: { redo: redoCopyEn } }, true, true);
}

if (i18n.isInitialized) register();
else i18n.on("initialized", register);
