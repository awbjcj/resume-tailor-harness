import { useTranslation } from "react-i18next";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  Archive,
  Mail,
  Bot,
  FileKey2,
  KeyRound,
  FileText,
  Paintbrush,
  PanelsTopLeft,
  Search,
  SlidersHorizontal,
  Sparkles,
  type LucideIcon,
} from "lucide-react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { cn } from "@/lib/utils";
import i18n from "@/i18n";

type SettingsNavItem = { to: string; label: string; icon: LucideIcon };

/** Group settings by the task they support, across desktop and mobile. */
export function getSettingsNavigation() {
  const groups = [
    {
      label: "Discovery",
      items: [
        { to: "/settings/search", label: "Search", icon: Search },
        { to: "/settings/sources", label: "Sources", icon: PanelsTopLeft },
        { to: "/settings/pruning", label: "Pruning", icon: SlidersHorizontal },
      ],
    },
    {
      label: "Resumes",
      items: [
        { to: "/settings/review", label: "Review panel", icon: Sparkles },
        { to: "/settings/style-guide", label: "Style guide", icon: Paintbrush },
        { to: "/settings/rendering", label: "Rendering", icon: FileText },
      ],
    },
    {
      label: "Applications",
      items: [
        { to: "/settings/application-profile", label: "Application profile", icon: FileText },
        { to: "/settings/password-manager", label: i18n.t("passwordManager.title"), icon: KeyRound },
        { to: "/settings/notifications", label: "Email & notifications", icon: Mail },
      ],
    },
    {
      label: "AI configuration",
      items: [
        { to: "/settings/keys", label: "API keys & models", icon: FileKey2 },
        { to: "/settings/agent-prompts", label: "Agent prompts", icon: Bot },
      ],
    },
    {
      label: "Workspace",
      items: [
        { to: "/settings/backup", label: "Backup", icon: Archive },
      ],
    },
  ] satisfies ReadonlyArray<{ label: string; items: ReadonlyArray<SettingsNavItem> }>;

  /** Flat projection of every settings destination, in group order. */
  const nav: ReadonlyArray<SettingsNavItem> = groups.flatMap(
    (group) => group.items,
  );
  return { groups, nav };
}

export function SettingsLayout() {
  useTranslation();
  const { groups, nav } = getSettingsNavigation();
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const selected = nav.find((item) => item.to === pathname.replace(/\/+$/, ""))?.to ?? nav[0].to;
  return (
    <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:gap-8">
      <aside className="min-w-0 lg:sticky lg:top-24 lg:w-64 lg:shrink-0">
        <Card size="sm" className="lg:max-h-[calc(100dvh-7rem)] lg:overflow-y-auto">
          <CardHeader className="border-b">
            <CardTitle>Settings</CardTitle>
            <CardDescription>
              Manage discovery, resumes, applications, and your workspace.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <nav aria-label="Settings">
              <div className="flex flex-col gap-2 lg:hidden">
                <label htmlFor="settings-section" className="text-sm font-medium">
                  Settings section
                </label>
                <select
                  id="settings-section"
                  value={selected}
                  onChange={(event) => void navigate(event.target.value)}
                  className="min-h-11 w-full min-w-0 rounded-lg border border-input bg-background px-3 py-2 text-base outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
                >
                  {groups.map((group) => (
                    <optgroup key={group.label} label={group.label}>
                      {group.items.map((item) => (
                        <option key={item.to} value={item.to}>{item.label}</option>
                      ))}
                    </optgroup>
                  ))}
                </select>
              </div>
              <div className="hidden flex-col gap-4 lg:flex">
              {groups.map((group, index) => (
                <div key={group.items[0].to} className="flex flex-col gap-1.5">
                  <div id={`settings-group-${index}`} className="px-3 text-xs font-semibold text-muted-foreground">
                    {group.label}
                  </div>
                  <ul aria-labelledby={`settings-group-${index}`} className="flex flex-col gap-1.5">
                    {group.items.map((item) => {
                      const Icon = item.icon;
                      return (
                        <li key={item.to} className="lg:w-full">
                          <NavLink
                            to={item.to}
                            className={({ isActive }) =>
                              cn(
                                "flex min-h-11 items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-muted-foreground outline-none transition-colors hover:bg-muted hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring lg:w-full",
                                isActive &&
                                  "bg-primary/8 font-medium text-foreground ring-1 ring-primary/20",
                              )
                            }
                          >
                            <Icon aria-hidden="true" className="size-4 shrink-0" />
                            <span className="min-w-0 [overflow-wrap:anywhere]">{item.label}</span>
                          </NavLink>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              ))}
              </div>
            </nav>
          </CardContent>
        </Card>
      </aside>
      <main
        aria-label="Settings panel"
        className="min-w-0 flex-1 rounded-xl bg-card px-4 py-5 ring-1 ring-foreground/10 sm:px-7 sm:py-8 xl:px-9"
      >
        <Outlet />
      </main>
    </div>
  );
}
