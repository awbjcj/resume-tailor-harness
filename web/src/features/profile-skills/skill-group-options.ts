import type { SearchGroup } from "@/components/ui/searchable-select";
import type { LibraryCategory, LibraryGroup } from "./SkillEditorFields";

export function skillGroupOptions(
  groups: (LibraryGroup & { originalLabel?: string })[],
  categories: (LibraryCategory & { originalLabel?: string })[],
): SearchGroup[] {
  const item = (group: (typeof groups)[number], parent?: string) => ({
    value: group.slug,
    label: group.label,
    keywords: [group.originalLabel, parent].filter((label): label is string => !!label),
  });
  const known = new Set(categories.map((category) => category.slug));
  return [
    ...categories.map((category) => ({
      id: category.slug,
      label: category.label,
      items: groups.filter((group) => group.category === category.slug).map((group) => item(group, category.originalLabel)),
    })),
    { id: "uncategorized-groups", items: groups.filter((group) => !known.has(group.category)).map((group) => item(group)) },
  ];
}
