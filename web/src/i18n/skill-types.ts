import { useTranslation } from "react-i18next";

// Shared with compact skill controls that do not load the full skill library.
export const skillTypesEn = { unspecified: "Not sure", hard: "Hard skill", soft: "Soft skill", domain: "Domain knowledge" };
export const skillTypesZh: typeof skillTypesEn = { unspecified: "未确定", hard: "硬技能", soft: "软技能", domain: "领域知识" };

export function useSkillTypeLabels() {
  const { i18n } = useTranslation();
  return i18n.resolvedLanguage?.startsWith("zh") ? skillTypesZh : skillTypesEn;
}
