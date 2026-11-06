import { useState } from "react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Archive, ArchiveRestore, Clock3, EllipsisVertical, Pencil, Plus, Trash2 } from "lucide-react";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuGroup, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { ListSearch } from "@/components/ui/list-search";
import { ListSection } from "@/components/ui/list-section";
import { listSearch } from "@/lib/list-search";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

export type ChatSessionHistoryItem = {
  id: string;
  title: string;
  detail: string;
  status: "active" | "ended";
  archived?: boolean;
};

type SessionAction = (sessionId: string) => void;

export function ChatSessionHistory({
  items,
  selectedId,
  onSelect,
  showArchived,
  onShowArchivedChange,
  isLoading = false,
  isError = false,
  onRetry,
  emptyMessage,
  createLabel,
  onCreate,
  createDisabled = false,
  onRename,
  onArchive,
  onUnarchive,
  onDelete,
  renamePending = false,
  deletePending = false,
  deleteTitle = "Delete this session?",
  deleteDescription = "This permanently removes the saved conversation. This cannot be undone.",
  ariaLabel = "Session history",
}: {
  items: ChatSessionHistoryItem[];
  selectedId: string | null;
  onSelect: (sessionId: string) => void;
  showArchived: boolean;
  onShowArchivedChange: (checked: boolean) => void;
  isLoading?: boolean;
  isError?: boolean;
  onRetry?: () => void;
  emptyMessage: ReactNode;
  createLabel?: string;
  onCreate?: () => void;
  createDisabled?: boolean;
  onRename?: (sessionId: string, title: string) => void;
  onArchive?: SessionAction;
  onUnarchive?: SessionAction;
  onDelete?: SessionAction;
  renamePending?: boolean;
  deletePending?: boolean;
  deleteTitle?: ReactNode | ((item: ChatSessionHistoryItem) => ReactNode);
  deleteDescription?: ReactNode | ((item: ChatSessionHistoryItem) => ReactNode);
  ariaLabel?: string;
}) {
  const { t } = useTranslation();
  const [search, setSearch] = useState("");
  const [pendingRename, setPendingRename] = useState<ChatSessionHistoryItem | null>(null);
  const [renameTitle, setRenameTitle] = useState("");
  const [pendingDelete, setPendingDelete] = useState<ChatSessionHistoryItem | null>(null);
  const resolvedDeleteTitle = typeof deleteTitle === "function"
    ? pendingDelete ? deleteTitle(pendingDelete) : null
    : deleteTitle;
  const resolvedDeleteDescription = typeof deleteDescription === "function"
    ? pendingDelete ? deleteDescription(pendingDelete) : null
    : deleteDescription;

  const matches = listSearch(search);
  const sections = [
    { id: "active", label: t("longLists.activeSessions") },
    { id: "ended", label: t("longLists.completedSessions") },
    { id: "archived", label: t("longLists.archivedSessions") },
  ].map(({ id, label }) => ({
    id,
    label,
    rows: items.filter((item) =>
      (item.archived ? "archived" : item.status) === id && matches(item.title, item.detail, label),
    ),
  }));
  const shown = sections.reduce((count, section) => count + section.rows.length, 0);
  return (
    <Card className="min-w-0 rounded-2xl shadow-none" role="region" aria-label={ariaLabel}>
      <CardHeader className="gap-3 border-b py-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Clock3 className="size-4 text-primary" aria-hidden="true" />
            <CardTitle className="text-base">Session history</CardTitle>
          </div>
          <div className="flex min-w-0 flex-wrap items-center gap-3">
            <label className="flex min-h-9 min-w-0 items-center gap-2 text-xs text-muted-foreground">
              <Checkbox checked={showArchived} onCheckedChange={(checked) => onShowArchivedChange(checked === true)} />
              Show archived
            </label>
            {onCreate && createLabel ? (
              <Button variant="outline" size="sm" className="h-auto min-h-9 max-w-full whitespace-normal text-left" disabled={createDisabled} onClick={onCreate}>
                <Plus aria-hidden="true" />
                {createLabel}
              </Button>
            ) : null}
          </div>
        </div>
      </CardHeader>
      <CardContent className="pt-1">
        {isLoading ? (
          <div className="space-y-2 py-3" role="status" aria-label="Loading sessions">
            <Skeleton className="h-14 w-full" />
            <Skeleton className="h-14 w-full" />
          </div>
        ) : null}
        {isError ? (
          <div className="flex flex-wrap items-center justify-between gap-3 py-4 text-sm text-destructive">
            <span>Sessions could not be loaded.</span>
            {onRetry ? <Button size="sm" variant="outline" onClick={onRetry}>Try again</Button> : null}
          </div>
        ) : null}
        {!isLoading && !isError && items.length === 0 ? (
          <p className="py-4 text-sm leading-6 text-muted-foreground">{emptyMessage}</p>
        ) : null}
        {!isLoading && !isError && items.length > 0 ? (
          <div className="space-y-2 py-3">
            <ListSearch value={search} onChange={setSearch} aria-label={t("longLists.searchSessions")} placeholder={t("longLists.searchSessions")} />
            <p role="status" className="text-sm text-muted-foreground empty:sr-only">
              {search.trim() ? shown ? t("longLists.results", { shown, total: items.length }) : t("longLists.noMatches") : null}
            </p>
            {sections.map(({ id, label, rows }) => rows.length ? (
              <ListSection key={id} label={label} count={rows.length} query={search.trim()}
                defaultOpen={items.length <= 10 || id === "active" || rows.some((item) => item.id === selectedId)}
                className="rounded-lg border bg-muted/20">
                <ul className="divide-y border-t px-3">
                  {rows.map((item) => (
                    <li key={item.id} className="flex items-center gap-3 py-3">
                      <button
                        type="button"
                        onClick={() => onSelect(item.id)}
                        className={cn(
                          "min-h-11 min-w-0 flex-1 rounded-sm text-left outline-none focus-visible:ring-2 focus-visible:ring-ring",
                          selectedId === item.id && "text-foreground",
                        )}
                        aria-current={selectedId === item.id ? "page" : undefined}
                      >
                        <span className="flex items-center gap-2 text-sm font-medium">
                          {item.status === "active" ? <span className="size-1.5 shrink-0 rounded-full bg-primary" aria-hidden="true" /> : null}
                          <span className="min-w-0 [overflow-wrap:anywhere]">{item.title}</span>
                        </span>
                        <span className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
                          <span className="min-w-0 [overflow-wrap:anywhere]">{item.detail}</span>
                          {selectedId === item.id ? <Badge aria-hidden variant="outline">Viewing</Badge> : null}
                        </span>
                      </button>
                      {onRename || onArchive || onUnarchive || onDelete ? (
                        <DropdownMenu>
                          <DropdownMenuTrigger render={<Button size="icon-lg" variant="ghost" aria-label={`Actions for ${item.title}`}><EllipsisVertical aria-hidden /></Button>} />
                          <DropdownMenuContent align="end">
                            <DropdownMenuGroup>
                              {onRename ? <DropdownMenuItem onClick={() => { setPendingRename(item); setRenameTitle(item.title); }}><Pencil />Rename</DropdownMenuItem> : null}
                              {item.status === "ended" && !item.archived && onArchive ? <DropdownMenuItem onClick={() => onArchive(item.id)}><Archive />Archive</DropdownMenuItem> : null}
                              {item.archived && onUnarchive ? <DropdownMenuItem onClick={() => onUnarchive(item.id)}><ArchiveRestore />Unarchive</DropdownMenuItem> : null}
                              {onDelete ? <DropdownMenuItem variant="destructive" onClick={() => setPendingDelete(item)}><Trash2 />Delete</DropdownMenuItem> : null}
                            </DropdownMenuGroup>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      ) : null}
                    </li>
                  ))}
                </ul>
              </ListSection>
            ) : null)}
          </div>
        ) : null}
      </CardContent>

      <Dialog open={pendingRename != null} onOpenChange={(open) => { if (!open) setPendingRename(null); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Rename session</DialogTitle>
            <DialogDescription>Choose a short name that will be easy to recognize in your history.</DialogDescription>
          </DialogHeader>
          <Input aria-label="Session title" autoFocus maxLength={120} value={renameTitle} onChange={(event) => setRenameTitle(event.target.value)} />
          <DialogFooter>
            <Button variant="ghost" onClick={() => setPendingRename(null)}>Cancel</Button>
            <Button
              disabled={!renameTitle.trim() || renamePending}
              onClick={() => {
                if (!pendingRename || !onRename) return;
                onRename(pendingRename.id, renameTitle.trim());
                setPendingRename(null);
              }}
            >
              Save title
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog open={pendingDelete != null} onOpenChange={(open) => { if (!open) setPendingDelete(null); }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{resolvedDeleteTitle}</AlertDialogTitle>
            <AlertDialogDescription>{resolvedDeleteDescription}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep session</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              disabled={deletePending}
              onClick={() => {
                if (!pendingDelete || !onDelete) return;
                onDelete(pendingDelete.id);
                setPendingDelete(null);
              }}
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}
