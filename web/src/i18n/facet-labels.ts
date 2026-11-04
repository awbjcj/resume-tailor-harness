import { fieldLabel } from "@/lib/format";
import type { FilterState } from "@/lib/filters/types";

// Only translate the app's closed vocabularies. Company names, skills,
// locations, source names, and unrecognized values may be user supplied.
const CHINESE_FACETS: Partial<Record<keyof FilterState, Record<string, string>>> = {
  status: {
    raw: "新获取", extracted: "已提取", rejected: "已拒绝", filtered: "已筛除",
    shortlisted: "已加入候选", approved: "已批准", tailored: "已定制", rendered: "已生成",
  },
  remote: { remote: "远程", hybrid: "混合办公", onsite: "现场办公" },
  sponsorship: { offered: "提供担保", silent: "未说明", denied: "不提供担保" },
  seniority: { junior: "初级", mid: "中级", senior: "高级", staff: "Staff 级", principal: "Principal 级" },
  employmentType: { full_time: "全职", contract: "合同工", internship: "实习", part_time: "兼职" },
};

const FORMATTED_FACETS = new Set<keyof FilterState>([
  "source", "remote", "sponsorship", "seniority", "employmentType", "industry", "companySize",
]);

export function facetLabel(key: keyof FilterState, value: string, language: string | undefined): string {
  const translated = language?.toLowerCase().startsWith("zh")
    ? CHINESE_FACETS[key]?.[value.toLowerCase()]
    : undefined;
  if (translated) return translated;
  return FORMATTED_FACETS.has(key) ? fieldLabel(value) : value.replace(/_/g, " ");
}
