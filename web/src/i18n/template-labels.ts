import translations from "./template-zh-CN.json";

type TemplateDisplay = {
  kind: "bundled" | "custom";
  title: string;
  description: string;
};

export function localizeTemplate<T extends TemplateDisplay>(item: T, language: string | undefined): T {
  if (!language?.toLowerCase().startsWith("zh")) return item;

  const labels = translations as Record<string, string>;
  return {
    ...item,
    title: item.kind === "bundled" ? labels[item.title] ?? item.title : item.title,
    description: item.kind === "bundled" || item.description === "Uploaded template"
      ? labels[item.description] ?? item.description
      : item.description,
  };
}
