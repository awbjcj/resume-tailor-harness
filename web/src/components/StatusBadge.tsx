import { Badge } from "@/components/ui/badge";
import { useTranslation } from "react-i18next";
import { CheckCheck, FileCheck2, ListChecks, Sparkles, X, type LucideIcon } from "lucide-react";

/* Pipeline stage is the one categorical axis in the product that needs six
   mutually distinguishable colours, so it maps to the verified `stage-*` ramp
   in index.css rather than to the four meaning tones. Each stage used to carry
   its own raw palette string plus a hand-written `dark:` twin — twelve values
   to keep in step by hand, in Tailwind hues that belonged to no other surface
   in the app. */
const STAGE_TONE: Record<string, string> = {
  raw: "stage-raw",
  extracted: "stage-raw",
  filtered: "stage-raw",
  shortlisted: "stage-shortlisted",
  approved: "stage-approved",
  tailored: "stage-tailored",
  rendered: "stage-rendered",
  rejected: "stage-rejected",
};

const STAGE_ICON: Record<string, LucideIcon> = {
  shortlisted: ListChecks,
  approved: CheckCheck,
  tailored: Sparkles,
  rendered: FileCheck2,
  rejected: X,
};

export function StatusBadge({ status }: { status: string }) {
  const { t } = useTranslation();
  const fallback = status.replace(/_/g, " ");
  const label = {
    raw: t("job.stages.raw"),
    extracted: t("job.stages.extracted"),
    filtered: t("job.stages.filtered"),
    rejected: t("job.stages.rejected"),
    shortlisted: t("job.stages.shortlisted"),
    approved: t("job.stages.approved"),
    tailored: t("job.stages.tailored"),
    rendered: t("job.stages.rendered"),
  }[status] ?? fallback;
  const Icon = STAGE_ICON[status];

  return (
    <Badge
      variant="outline"
      className="tone-chip h-6 gap-1.5 rounded-full px-2.5 text-xs font-medium tracking-normal"
      data-tone={STAGE_TONE[status] ?? "stage-raw"}
    >
      {Icon && <Icon aria-hidden="true" />}
      {label}
    </Badge>
  );
}
