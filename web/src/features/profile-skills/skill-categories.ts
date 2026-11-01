export type SkillCategory = "unspecified" | "hard" | "soft" | "domain";

export const SKILL_CATEGORIES: SkillCategory[] = ["unspecified", "hard", "soft", "domain"];

export function skillCategoryValue(value: string | null | undefined): SkillCategory {
  return value === "hard" || value === "soft" || value === "domain"
    ? value
    : "unspecified";
}
