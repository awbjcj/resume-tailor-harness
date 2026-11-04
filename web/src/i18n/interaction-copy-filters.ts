import i18n from "i18next";

export const filtersCopyEn = {
  title: "Filter by {{label}}",
  search: "Search {{label}}...",
  searchAria: "Search {{label}}",
  empty: "No matching {{label}}",
  options: "{{label}} options",
  clear: "Clear {{label}} filter",
  done: "Done filtering {{label}}",
  matching: "{{count}} matching",
};

function register() {
  i18n.addResourceBundle("en", "translation", { interactionCopy: { filters: filtersCopyEn } }, true, true);
}

if (i18n.isInitialized) register();
else i18n.on("initialized", register);
