import i18n from "i18next";

export const selectionCopyEn = {
  count: "{{count}} selected",
  loaded: "All {{count}} loaded items are selected.",
  selectMatching: "Select all {{count}} matching this filter",
  selectVersions: "Select all deletable versions",
  selectLetters: "Select all deletable cover letters",
  deleteSelected: "Delete selected",
  deleteSelectedCount: "Delete {{count}} selected",
  deleteVersion_one: "Delete {{count}} version?",
  deleteVersion_other: "Delete {{count}} versions?",
  deleteLetter_one: "Delete {{count}} cover letter?",
  deleteLetter_other: "Delete {{count}} cover letters?",
  versionDescription_one: "The version and any rendered PDF will be removed. This cannot be undone.",
  versionDescription_other: "The versions and any rendered PDFs will be removed. This cannot be undone.",
  letterDescription_one: "The cover letter and any rendered PDF will be removed. This cannot be undone.",
  letterDescription_other: "The cover letters and any rendered PDFs will be removed. This cannot be undone.",
  affected_one: "{{formattedCount}} job affected",
  affected_other: "{{formattedCount}} jobs affected",
  skipped: "{{count}} skipped",
  preview: "{{affected}}{{skipped}}.",
  approveJobs_one: "Approve {{formattedCount}} selected job?",
  approveJobs_other: "Approve {{formattedCount}} selected jobs?",
  archiveJobs_one: "Archive {{formattedCount}} selected job?",
  archiveJobs_other: "Archive {{formattedCount}} selected jobs?",
  restoreJobs_one: "Restore {{formattedCount}} selected job?",
  restoreJobs_other: "Restore {{formattedCount}} selected jobs?",
  deleteJobs_one: "Delete {{formattedCount}} selected job?",
  deleteJobs_other: "Delete {{formattedCount}} selected jobs?",
  setStatus_one: "Set {{formattedCount}} selected job to {{status}}?",
  setStatus_other: "Set {{formattedCount}} selected jobs to {{status}}?",
  bulkArchive_one: "Archived {{formattedCount}} job",
  bulkArchive_other: "Archived {{formattedCount}} jobs",
  bulkRestore_one: "Restored {{formattedCount}} job",
  bulkRestore_other: "Restored {{formattedCount}} jobs",
  bulkDelete_one: "Deleted {{formattedCount}} job",
  bulkDelete_other: "Deleted {{formattedCount}} jobs",
  bulkApprove_one: "Approved {{formattedCount}} job",
  bulkApprove_other: "Approved {{formattedCount}} jobs",
  bulkSetStatus_one: "Updated the status of {{formattedCount}} job",
  bulkSetStatus_other: "Updated the status of {{formattedCount}} jobs",
  trayCount: "{{count}} selected",
  trayOpen: "Selection ({{count}})",
};

function register() {
  i18n.addResourceBundle("en", "translation", { interactionCopy: { selection: selectionCopyEn } }, true, true);
}

if (i18n.isInitialized) register();
else i18n.on("initialized", register);
