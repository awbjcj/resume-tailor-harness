import { Link } from "react-router-dom";
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatCalendarDate } from "@/lib/calendar-date";
import {
  ApplicationTimelineStage,
  applicationModalityLabel,
  applicationPlatformLabel,
  applicationResultLabel,
  applicationStageLabel,
  applicationStatusLabel,
  isActiveApplicationStatus,
} from "./application-labels";
import type { ApplicationsTableData } from "./use-applications";

type PivotCell = ApplicationsTableData["rows"][number]["cells"][string];

const FIXED_STAGES = [
  ApplicationTimelineStage.ApplicationSubmitted,
  ApplicationTimelineStage.RecruiterScreen,
  ApplicationTimelineStage.OnlineAssessment,
  ApplicationTimelineStage.Questionnaire,
  ApplicationTimelineStage.TechnicalPhoneScreen,
] as const;

const LATE_STAGES = [
  ApplicationTimelineStage.SystemDesign,
  ApplicationTimelineStage.Behavioral,
  ApplicationTimelineStage.HiringManager,
  ApplicationTimelineStage.OnsiteLoop,
  ApplicationTimelineStage.TeamMatch,
  ApplicationTimelineStage.OfferReceived,
  ApplicationTimelineStage.Rejected,
  ApplicationTimelineStage.Withdrawn,
] as const;

function compactDate(value: string, allDay = false): string {
  return formatCalendarDate(value, allDay, { month: "short", day: "numeric" });
}

function metadata(t: TFunction, cell: PivotCell): string {
  return [
    applicationResultLabel(t, cell.result),
    cell.modality ? applicationModalityLabel(t, cell.modality) : null,
    cell.platform ? applicationPlatformLabel(t, cell.platform) : null,
    cell.platformOther,
    cell.interviewers,
  ].filter(Boolean).join(" · ");
}

function StageCell({ cell, label }: { cell?: PivotCell; label: string }) {
  const { t } = useTranslation();
  if (!cell?.occurredAt) return <span className="text-muted-foreground">—</span>;
  const detail = metadata(t, cell);
  const detailLabel = t("applicationTimeline.details", { stage: label });
  return (
    <Popover>
      <PopoverTrigger
        type="button"
        aria-label={detailLabel}
        className="min-h-9 cursor-pointer rounded px-1 tabular-nums outline-none hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring active:bg-muted"
      >
        {compactDate(cell.occurredAt, cell.allDay)}
      </PopoverTrigger>
      <PopoverContent
        aria-label={detailLabel}
        className="w-max max-w-[min(16rem,var(--available-width))] gap-0 px-2.5 py-2 text-xs leading-5 whitespace-normal [overflow-wrap:anywhere] data-open:animate-none data-closed:animate-none"
      >
        {detail || t("applicationTimeline.noAdditionalDetails")}
      </PopoverContent>
    </Popover>
  );
}

export function ApplicationsTable({
  table,
  groupByStatus = false,
  selectedJobIds = [],
  onToggleSelection,
}: {
  table: ApplicationsTableData;
  groupByStatus?: boolean;
  selectedJobIds?: readonly number[];
  onToggleSelection?: (jobId: number) => void;
}) {
  const { t } = useTranslation();
  if (table.rows.length === 0) {
    return (
      <div className="rounded-lg border border-dashed bg-muted/20 px-5 py-10 text-center text-sm text-muted-foreground">
        {t("applicationTimeline.empty")}
      </div>
    );
  }

  const technicalStageLabel = (index: number) => t("applicationTimeline.technicalRound", { number: index + 1 });
  const technicalStages = Array.from(
    { length: table.technicalRoundColumns },
    (_, index) => `technical_round_${index + 1}`,
  );
  const stages = [...FIXED_STAGES, ...technicalStages, ...LATE_STAGES];
  const groups = groupByStatus
    ? [...new Set(table.rows.map((row) => row.status))].map((status) => ({ status, rows: table.rows.filter((row) => row.status === status) }))
    : [{ status: null, rows: table.rows }];
  // Keep the comparison width in sync with the company's sticky offset;
  // translated headers must not shrink it and push the company over the role.
  const comparisonColumnClassName = "w-20 min-w-20 max-w-20 bg-card md:sticky md:left-0";
  const companyColumnClassName = `w-44 min-w-44 max-w-44 bg-card md:sticky ${onToggleSelection ? "md:left-20" : "md:left-0"}`;

  return (
    <div className="min-w-0 rounded-lg border bg-card shadow-card">
      <Table className="min-w-[1180px] caption-top">
        <caption className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">
          {t("applicationTimeline.headers.caption")}
        </caption>
        <TableHeader>
          <TableRow>
            {onToggleSelection ? (
              <TableHead className={`${comparisonColumnClassName} md:z-20`}>
                {t("applications.comparison.column")}
              </TableHead>
            ) : null}
            <TableHead className={`${companyColumnClassName} md:z-10`}>{t("applicationTimeline.headers.company")}</TableHead>
            <TableHead className="w-72 min-w-72">{t("applicationTimeline.headers.role")}</TableHead>
            {!groupByStatus ? <TableHead>{t("applicationTimeline.headers.status")}</TableHead> : null}
            {stages.map((key) => (
              <TableHead key={key}>
                {key.startsWith("technical_round_")
                  ? technicalStageLabel(Number(key.slice("technical_round_".length)) - 1)
                  : applicationStageLabel(t, key)}
              </TableHead>
            ))}
            <TableHead>{t("applicationTimeline.headers.deadline")}</TableHead>
            <TableHead>{t("applicationTimeline.headers.totalComp")}</TableHead>
            <TableHead>{t("applicationTimeline.headers.other")}</TableHead>
          </TableRow>
        </TableHeader>
        {groups.map(({ status, rows }) => (
          <TableBody key={status ?? "all"}>
            {status !== null ? (
              <TableRow className="bg-muted/45">
                <TableHead scope="rowgroup" colSpan={stages.length + (onToggleSelection ? 6 : 5)} className="px-4 font-semibold">
                  <span className="md:sticky md:left-4">
                    {applicationStatusLabel(t, status)}{" "}
                    <span className="ml-1 text-xs font-normal tabular-nums text-muted-foreground">{rows.length}</span>
                  </span>
                </TableHead>
              </TableRow>
            ) : null}
            {rows.map((row) => {
              const canCompare = isActiveApplicationStatus(row.status);
              return (
                <TableRow key={row.jobId}>
                  {onToggleSelection ? (
                    <TableCell className={`${comparisonColumnClassName} md:z-10`}>
                      <input
                        type="checkbox"
                        checked={selectedJobIds.includes(row.jobId)}
                        disabled={!canCompare}
                        aria-label={
                          canCompare
                            ? t("applications.comparison.selectRole", {
                                company: row.company || t("applicationTimeline.unknownCompany"),
                                role: row.title || t("applications.comparison.unknownRole"),
                              })
                            : t("applications.comparison.terminalRole", {
                                company: row.company || t("applicationTimeline.unknownCompany"),
                                role: row.title || t("applications.comparison.unknownRole"),
                              })
                        }
                        onChange={() => onToggleSelection(row.jobId)}
                        className="size-4 rounded border-input accent-primary"
                      />
                    </TableCell>
                  ) : null}
                  <TableCell className={`${companyColumnClassName} font-medium md:z-[1]`}>
                    <Link
                      to={`/pipeline?job=${row.jobId}`}
                      className="block w-40 whitespace-normal text-primary underline-offset-4 [overflow-wrap:anywhere] hover:underline"
                    >
                      {row.company || t("applicationTimeline.unknownCompany")}
                    </Link>
                  </TableCell>
                  <TableCell className="w-72 min-w-72 whitespace-normal">
                    <div className="w-68 leading-relaxed [overflow-wrap:anywhere]">{row.title || "—"}</div>
                  </TableCell>
                  {!groupByStatus ? <TableCell><Badge variant="outline">{applicationStatusLabel(t, row.status)}</Badge></TableCell> : null}
                  {stages.map((key) => {
                    const isLastVisibleRound = key === `technical_round_${table.technicalRoundColumns}`;
                    return (
                      <TableCell key={key} className="whitespace-nowrap">
                        <div className="flex items-center gap-1.5">
                          <StageCell
                            cell={row.cells[key]}
                            label={
                              key.startsWith("technical_round_")
                                ? t("applicationTimeline.technicalRoundDetails", { number: key.slice("technical_round_".length) })
                                : applicationStageLabel(t, key)
                            }
                          />
                          {isLastVisibleRound && row.overflowRounds > 0 ? (
                            <Badge variant="secondary">+{row.overflowRounds}</Badge>
                          ) : null}
                        </div>
                      </TableCell>
                    );
                  })}
                  <TableCell className="whitespace-nowrap">
                    {row.offerDeadline
                      ? compactDate(row.offerDeadline, row.cells.offer_deadline?.allDay)
                      : "—"}
                  </TableCell>
                  <TableCell className="whitespace-nowrap tabular-nums">
                    {row.totalComp != null
                      ? `${row.totalComp.toLocaleString()} ${row.compCurrency ?? ""}`.trim()
                      : "—"}
                  </TableCell>
                  <TableCell>{row.customCount ? t("applicationTimeline.otherCount", { count: row.customCount }) : "—"}</TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        ))}
      </Table>
    </div>
  );
}
