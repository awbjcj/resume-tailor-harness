import { useMemo, useState } from "react";
import { ChevronLeft, ChevronRight, CircleAlert, Download, GitCompareArrows, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { PageHeader } from "@/components/PageHeader";
import { BoardSkeleton } from "@/components/skeletons";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ListSearch } from "@/components/ui/list-search";
import { openDownload } from "@/lib/api/client";
import { listSearch } from "@/lib/list-search";
import { applicationStatusLabel, isActiveApplicationStatus } from "./application-labels";
import { ApplicationsTable } from "./ApplicationsTable";
import { RoleComparisonTable } from "./RoleComparisonTable";
import { useApplications } from "./use-applications";
import { useRoleComparison } from "./use-role-comparison";

type SortOrder = "newest" | "company-asc" | "company-desc" | "status";
const PAGE_SIZE = 40;
const FILTER_CLASS = "h-11 w-full min-w-0 rounded-lg border border-input bg-background px-3 focus-visible:outline-2 focus-visible:outline-ring dark:bg-input/30";

export function ApplicationsPage() {
  const { t } = useTranslation();
  const query = useApplications();
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("all");
  const [sort, setSort] = useState<SortOrder>("newest");
  const [page, setPage] = useState(0);
  const [selectedJobIds, setSelectedJobIds] = useState<number[]>([]);
  const comparison = useRoleComparison();
  const data = query.data;

  const visible = useMemo(() => {
    if (!data) return null;
    const matches = listSearch(search);
    const rows = data.rows.filter(
      (row) =>
        (status === "all" || row.status === status) &&
        matches(row.company, row.title),
    );
    if (sort !== "newest") {
      rows.sort((left, right) => {
        if (sort === "status") return left.status.localeCompare(right.status);
        const compared = (left.company ?? "").localeCompare(right.company ?? "");
        return sort === "company-desc" ? -compared : compared;
      });
    }
    return { ...data, rows };
  }, [data, search, sort, status]);

  if (!visible || !data) {
    return (
      <div className="flex min-w-0 flex-col gap-6">
        <PageHeader title="Applications" />
        {query.isError ? (
          <Alert variant="destructive" className="items-start p-4">
            <CircleAlert aria-hidden />
            <AlertTitle>{t("applications.loadError")}</AlertTitle>
            <AlertDescription>
              <Button className="mt-1 w-fit" variant="outline" disabled={query.isFetching} onClick={() => void query.refetch()}>
                {t("deferred.retry")}
              </Button>
            </AlertDescription>
          </Alert>
        ) : <BoardSkeleton />}
      </div>
    );
  }
  const pages = Math.max(1, Math.ceil(visible.rows.length / PAGE_SIZE));
  const currentPage = Math.min(page, pages - 1);
  const pageRows = visible.rows.slice(currentPage * PAGE_SIZE, (currentPage + 1) * PAGE_SIZE);
  const statuses = [...new Set(data.rows.map((row) => row.status))].sort();
  const selected = selectedJobIds.filter((id) =>
    data.rows.some((row) => row.jobId === id && isActiveApplicationStatus(row.status)),
  );
  if (selected.length !== selectedJobIds.length) setSelectedJobIds(selected);
  const currentComparison = comparison.variables?.length === selected.length &&
    selected.every((id, index) => id === comparison.variables?.[index]);
  const updateSearch = (value: string) => {
    setSearch(value);
    setPage(0);
  };
  const download = (shape: "wide" | "long") => {
    void openDownload(`/api/applications.csv?shape=${shape}`).catch((error: Error) =>
      toast.error(error.message),
    );
  };
  const toggleSelection = (jobId: number) => {
    if (selected.length === 3 && !selected.includes(jobId)) {
      toast.error("Compare up to three roles at a time");
      return;
    }
    comparison.reset();
    setSelectedJobIds(selected.includes(jobId) ? selected.filter((value) => value !== jobId) : [...selected, jobId]);
  };

  return (
    <div className="flex min-w-0 flex-col gap-6">
      <PageHeader
        title="Applications"
        actions={<>
          <Button variant="outline" size="lg" onClick={() => download("wide")}><Download aria-hidden="true" />Export grid</Button>
          <Button variant="outline" size="lg" onClick={() => download("long")}><Download aria-hidden="true" />Export events</Button>
        </>}
      />
      <section aria-label="Application controls" className="@container rounded-lg border bg-card p-4 shadow-card">
        <div className="grid items-end gap-3 @sm:grid-cols-2 @2xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)]">
          <div className="grid min-w-0 gap-1.5 text-sm font-medium @sm:col-span-2 @2xl:col-span-1">
            <label htmlFor="application-company-search">Company or role</label>
            <ListSearch
              id="application-company-search"
              value={search}
              placeholder="Search applications"
              onChange={updateSearch}
              onKeyDown={(event) => {
                if (event.key === "Escape") updateSearch("");
              }}
            />
          </div>
          <label className="grid min-w-0 gap-1.5 text-sm font-medium">
            {t("applications.status")}
            <select className={FILTER_CLASS} value={status} onChange={(event) => { setStatus(event.target.value); setPage(0); }}>
              <option value="all">{t("applications.allStatuses")}</option>
              {statuses.map((value) => <option key={value} value={value}>{applicationStatusLabel(t, value)}</option>)}
            </select>
          </label>
          <label className="grid min-w-0 gap-1.5 text-sm font-medium">
            {t("applications.sortBy")}
            <select className={FILTER_CLASS} value={sort} onChange={(event) => { setSort(event.target.value as SortOrder); setPage(0); }}>
              <option value="newest">{t("applications.sortOptions.newest")}</option>
              <option value="company-asc">{t("applications.sortOptions.companyAscending")}</option>
              <option value="company-desc">{t("applications.sortOptions.companyDescending")}</option>
              <option value="status">{t("applications.sortOptions.status")}</option>
            </select>
          </label>
        </div>
      </section>
      <section aria-label="Role comparison controls" className="flex flex-wrap items-center gap-3 rounded-lg border bg-card p-4 shadow-card">
        <div className="min-w-0 flex-1 basis-52">
          <p className="text-sm font-semibold">Compare roles</p>
          <p className="text-sm text-muted-foreground">
            {`Select two or three application rows. ${selected.length} selected.`}
          </p>
        </div>
        {selected.length ? (
          <Button
            type="button"
            variant="ghost"
            onClick={() => {
              setSelectedJobIds([]);
              comparison.reset();
            }}
          >
            <X aria-hidden="true" />
            Clear
          </Button>
        ) : null}
        <Button
          type="button"
          disabled={selected.length < 2 || (currentComparison && comparison.isPending)}
          onClick={() => comparison.mutate(selected)}
        >
          <GitCompareArrows aria-hidden="true" />
          {currentComparison && comparison.isPending ? "Comparing…" : "Compare selected"}
        </Button>
      </section>
      {currentComparison && comparison.isError ? (
        <p role="alert" className="text-sm text-destructive">
          Role comparison could not be loaded. The selected applications are unchanged.
        </p>
      ) : null}
      {currentComparison && comparison.data ? <RoleComparisonTable comparison={comparison.data} /> : null}
      <div className="min-w-0 space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm text-muted-foreground" role="status">
            {t("applications.showing", { shown: visible.rows.length, total: data.rows.length })}
          </p>
          {pages > 1 ? (
            <nav aria-label={t("applications.pages")} className="flex flex-wrap items-center gap-2">
              <span role="status" className="text-sm tabular-nums text-muted-foreground">{t("applications.pageNumber", { page: currentPage + 1, total: pages })}</span>
              <Button type="button" variant="outline" size="icon-lg" aria-label={t("applications.previousPage")} disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}>
                <ChevronLeft aria-hidden />
              </Button>
              <Button type="button" variant="outline" size="icon-lg" aria-label={t("applications.nextPage")} disabled={currentPage === pages - 1} onClick={() => setPage(currentPage + 1)}>
                <ChevronRight aria-hidden />
              </Button>
            </nav>
          ) : null}
        </div>
        {data.rows.length > 0 && pageRows.length === 0 ? (
          <div className="rounded-lg border border-dashed bg-muted/20 px-5 py-10 text-center text-sm text-muted-foreground">
            <p>{t("applications.noMatches")}</p>
            <Button variant="link" onClick={() => {
              updateSearch("");
              setStatus("all");
              document.getElementById("application-company-search")?.focus();
            }}>{t("applications.clearFilters")}</Button>
          </div>
        ) : (
          <ApplicationsTable
            table={{ ...visible, rows: pageRows }}
            groupByStatus={sort === "status"}
            selectedJobIds={selected}
            onToggleSelection={toggleSelection}
          />
        )}
      </div>
    </div>
  );
}
