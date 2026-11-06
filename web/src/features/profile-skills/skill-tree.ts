import type { LibraryCategory, LibraryGroup, LibraryRow } from "./SkillEditorFields";

export type SkillBranch = {
  category: LibraryCategory;
  groups: { group: LibraryGroup; rows: LibraryRow[] }[];
  count: number;
};

export type SkillDisclosure = (kind: "category" | "group", slug: string) => {
  browseOpen: boolean | undefined;
  onBrowseOpenChange: (open: boolean) => void;
};

export function buildSkillTree(
  categories: LibraryCategory[],
  groups: LibraryGroup[],
  rows: LibraryRow[],
  groupOf: (row: LibraryRow) => string,
  scope: { category: string; group: string; showEmpty: boolean },
): SkillBranch[] {
  const rowsByGroup = new Map<string, LibraryRow[]>();
  for (const row of rows) {
    const slug = groupOf(row);
    const members = rowsByGroup.get(slug) ?? [];
    members.push(row);
    rowsByGroup.set(slug, members);
  }
  return categories.flatMap((category) => {
    if (scope.category !== "all" && category.slug !== scope.category) return [];
    const children = groups.flatMap((group) => {
      if (group.category !== category.slug || (scope.group !== "all" && group.slug !== scope.group)) return [];
      const members = rowsByGroup.get(group.slug) ?? [];
      return members.length || scope.showEmpty ? [{ group, rows: members }] : [];
    });
    if (!children.length && (!scope.showEmpty || scope.group !== "all")) return [];
    return [{ category, groups: children, count: children.reduce((total, child) => total + child.rows.length, 0) }];
  });
}
