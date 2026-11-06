import type { SearchGroup } from "@/components/ui/searchable-select";
import { UNASSIGNED_ID, type CategoryRow } from "../aggregate";

export function domainSearchGroups(categories: CategoryRow[], sourceDomainId?: string): SearchGroup[] {
  return categories.map((category) => ({
    id: category.slug,
    label: category.label,
    items: category.domains
      .filter((domain) => domain.id !== UNASSIGNED_ID && domain.id !== sourceDomainId)
      .map((domain) => ({ value: domain.id, label: domain.label })),
  }));
}
