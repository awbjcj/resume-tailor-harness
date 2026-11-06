import { PageHeader } from "@/components/PageHeader";
import { useTranslation } from "react-i18next";
import { BoardSkeleton } from "@/components/skeletons";
import { JourneyRail } from "@/features/journey/JourneyRail";
import { formatUserDate } from "@/lib/date-time";

import { ActionQueue } from "./ActionQueue";
import { AttentionCard } from "./AttentionCard";
import { DeskHealth } from "./DeskHealth";
import { InProgressCard } from "./InProgressCard";
import { InsightsCard } from "./InsightsCard";
import { RecentRuns } from "./RecentRuns";
import { QuickAccess } from "./QuickAccess";
import { StageRail } from "./StageRail";
import { UpcomingCard } from "./UpcomingCard";
import { useDashboardSummary } from "./use-dashboard-summary";

export function heroTitle(waiting: number): string {
  if (waiting === 0) return "Nothing is waiting on you";
  return `${waiting} job${waiting === 1 ? " is" : "s are"} waiting on you`;
}

export function DashboardPage() {
  const { t, i18n } = useTranslation();
  const { data: summary, isPending } = useDashboardSummary();
  if (isPending || !summary) return <BoardSkeleton />;

  const waiting = Object.values(summary.queues).reduce((a, b) => a + b, 0);
  // rejected is terminal-negative and never appears on the rail/queues (see
  // StageRail), so it must not count toward "the funnel has jobs in it".
  const totalJobs = Object.entries(summary.statusCounts).reduce(
    (sum, [status, count]) => (status === "rejected" ? sum : sum + count),
    0,
  );
  const date = formatUserDate(new Date(), i18n.resolvedLanguage, {
    month: "short",
    day: "numeric",
  });

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={waiting === 0
          ? t("dashboard.waiting_zero", { count: waiting })
          : waiting === 1
            ? t("dashboard.waiting_one", { count: waiting })
            : t("dashboard.waiting_other", { count: waiting })}
        meta={<time dateTime={new Date().toLocaleDateString("en-CA")}>{date}</time>}
      />
      {totalJobs > 0 && <ActionQueue summary={summary} />}
      <JourneyRail />
      {totalJobs > 0 && <StageRail summary={summary} />}
      <aside
        aria-label={t("dashboard.systemStatus")}
        className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,16rem),1fr))] items-stretch gap-4 empty:hidden"
      >
        <InProgressCard summary={summary} />
        <InsightsCard summary={summary} />
        <DeskHealth />
      </aside>
      <UpcomingCard events={summary.upcomingEvents ?? []} />
      <AttentionCard />
      <RecentRuns />
      <QuickAccess />
    </div>
  );
}
