import i18n from "i18next";

export const sponsorshipCopyEn = {
  filings_one: "{{period}}: {{count}} cumulative LCA case",
  filings_other: "{{period}}: {{count}} cumulative LCA cases",
  notReported: "{{period}}: case count not reported",
  cases: "Cumulative LCA cases",
  certifiedCases: "Certified LCA cases",
  deniedCases: "Denied LCA cases",
  snapshot: "Disclosure snapshot",
  trendTitle: "Fiscal-year-to-date LCA snapshots",
  trendScope: "Counts are cumulative within each fiscal year, not single-quarter applications. Do not add overlapping snapshots.",
  legacy: "The previous check did not verify the count basis. Run a new check to see these figures.",
};

function register() {
  i18n.addResourceBundle("en", "translation", { interactionCopy: { sponsorship: sponsorshipCopyEn } }, true, true);
}

if (i18n.isInitialized) register();
else i18n.on("initialized", register);
