import {
  ArrowUpRight,
  FileKey2,
  PanelsTopLeft,
  Search,
  Sparkles,
  Wrench,
  type LucideIcon,
} from "lucide-react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";

type Shortcut = {
  to: string;
  label: string;
  detail: string;
  labelKey: `dashboard.shortcuts.${"sources" | "search" | "review" | "skills" | "keys"}`;
  detailKey: `dashboard.shortcuts.${"sourcesDetail" | "searchDetail" | "reviewDetail" | "skillsDetail" | "keysDetail"}`;
  icon: LucideIcon;
};

const SHORTCUTS: Shortcut[] = [
  {
    to: "/settings/sources",
    label: "Sources",
    detail: "Manage job feeds",
    labelKey: "dashboard.shortcuts.sources",
    detailKey: "dashboard.shortcuts.sourcesDetail",
    icon: PanelsTopLeft,
  },
  {
    to: "/settings/search",
    label: "Search settings",
    detail: "Tune discovery filters",
    labelKey: "dashboard.shortcuts.search",
    detailKey: "dashboard.shortcuts.searchDetail",
    icon: Search,
  },
  {
    to: "/settings/review",
    label: "Review workflow",
    detail: "Configure tailoring checks",
    labelKey: "dashboard.shortcuts.review",
    detailKey: "dashboard.shortcuts.reviewDetail",
    icon: Sparkles,
  },
  {
    to: "/profile?tab=skills",
    label: "Profile skills",
    detail: "Tune skill groups",
    labelKey: "dashboard.shortcuts.skills",
    detailKey: "dashboard.shortcuts.skillsDetail",
    icon: Wrench,
  },
  {
    to: "/settings/keys",
    label: "API keys",
    detail: "Connect model providers",
    labelKey: "dashboard.shortcuts.keys",
    detailKey: "dashboard.shortcuts.keysDetail",
    icon: FileKey2,
  },
];

export function QuickAccess() {
  const { t } = useTranslation();
  return (
    <nav aria-label={t("dashboard.shortcutsLabel")} className="overflow-hidden rounded-xl border bg-card/70 shadow-card">
      <div className="flex items-center justify-between gap-4 border-b bg-muted/35 px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold">{t("dashboard.quickAccess")}</span>
          <span className="hidden text-xs text-muted-foreground sm:inline">{t("dashboard.quickAccessHint")}</span>
        </div>
        <ArrowUpRight className="size-4 text-muted-foreground" aria-hidden="true" />
      </div>
      <div className="grid sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-5">
        {SHORTCUTS.map((shortcut) => (
          <Link
            key={shortcut.to}
            to={shortcut.to}
            aria-label={t("dashboard.openShortcut", {
              label: t(shortcut.labelKey),
              detail: t(shortcut.detailKey),
            })}
            className={cn(
              "group flex min-h-18 items-center gap-3 px-4 py-3 outline-none transition-[background-color,color,transform] duration-150 ease-out-strong hover:bg-accent/55 active:scale-[0.99] focus-visible:z-10 focus-visible:ring-[3px] focus-visible:ring-ring/50 motion-reduce:transform-none",
              "border-b sm:[&:nth-child(odd)]:border-r lg:[&:nth-child(odd)]:border-r-0 lg:[&:not(:nth-child(3n))]:border-r",
              "2xl:border-b-0 2xl:border-r 2xl:[&:nth-child(3n)]:border-r 2xl:last:border-r-0",
            )}
          >
            <span className="flex size-8 shrink-0 items-center justify-center rounded-lg border bg-background text-muted-foreground group-hover:text-foreground">
              <shortcut.icon className="size-4" aria-hidden="true" />
            </span>
            <span className="min-w-0 flex-1">
              <span className="flex items-center gap-2 text-sm font-medium">{t(shortcut.labelKey)}</span>
              <span className="block text-xs leading-4 text-muted-foreground">{t(shortcut.detailKey)}</span>
            </span>
            <ArrowUpRight className="size-3.5 shrink-0 text-muted-foreground/70" aria-hidden="true" />
          </Link>
        ))}
      </div>
    </nav>
  );
}
