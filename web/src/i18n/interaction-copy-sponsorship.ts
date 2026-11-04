import i18n from "i18next";

export const sponsorshipCopyEn = {
  filings_one: "{{period}}: {{count}} H-1B filing",
  filings_other: "{{period}}: {{count}} H-1B filings",
};

function register() {
  i18n.addResourceBundle("en", "translation", { interactionCopy: { sponsorship: sponsorshipCopyEn } }, true, true);
}

if (i18n.isInitialized) register();
else i18n.on("initialized", register);
