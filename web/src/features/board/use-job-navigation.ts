import { useCallback, useEffect, useState } from "react";

export type JobNavPagination = {
  hasNextPage: boolean;
  isFetchingNextPage: boolean;
  fetchNextPage: () => void;
};

export type JobNavigation = {
  hasPrev: boolean;
  hasNext: boolean;
  isLoadingNext: boolean;
  goPrev: () => void;
  goNext: () => void;
};

/**
 * Board-agnostic prev/next navigation over a list of loaded job ids.
 *
 * The `?job=` URL param (mirrored into `currentId`) is the source of truth for
 * which job is open, so navigating just calls `onNavigate(id)` — the caller
 * rewrites the param and the modal re-reads it.
 *
 * For flat paginated boards, pass `pagination`: when Next is pressed on the
 * last loaded row and more pages exist, the hook fetches the next page and
 * advances to its first row once the rows arrive. Boards without pagination
 * (e.g. Pipeline's per-stage sections) omit it, so Next simply disables at the
 * loaded edge.
 */
export function useJobNavigation(
  orderedIds: number[],
  currentId: number | null,
  onNavigate: (id: number) => void,
  pagination?: JobNavPagination,
): JobNavigation {
  const index = currentId == null ? -1 : orderedIds.indexOf(currentId);
  const [pendingAdvance, setPendingAdvance] = useState<{
    id: number;
    sawFetch: boolean;
  } | null>(null);
  const isFetching = pagination?.isFetchingNextPage ?? false;
  const hasNextPage = pagination?.hasNextPage ?? false;

  if (pendingAdvance && !pendingAdvance.sawFetch && isFetching) {
    setPendingAdvance({ ...pendingAdvance, sawFetch: true });
  }

  const hasPrev = index > 0;
  const hasNext =
    index >= 0 &&
    (index < orderedIds.length - 1 || (pagination?.hasNextPage ?? false));

  // A page we requested has landed: advance to the row after the current
  // one. If the modal closed (or jumped elsewhere) while the fetch was in
  // flight, there is nothing to advance from, so drop the request instead of
  // leaving it to fire a surprise navigation whenever the index next lines up.
  useEffect(() => {
    if (!pendingAdvance) return;
    if (index < 0 || currentId !== pendingAdvance.id) {
      // Intentional: this effect exists to synchronize with the external
      // fetch landing (orderedIds growing); clearing the flag here, not in
      // render, is the correct place once that external event resolves.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setPendingAdvance(null);
    } else if (index < orderedIds.length - 1) {
      setPendingAdvance(null);
      onNavigate(orderedIds[index + 1]);
    } else if (!hasNextPage || (pendingAdvance.sawFetch && !isFetching)) {
      setPendingAdvance(null);
    }
  }, [pendingAdvance, orderedIds, index, currentId, onNavigate, hasNextPage, isFetching]);

  const goPrev = useCallback(() => {
    if (index > 0) onNavigate(orderedIds[index - 1]);
  }, [index, orderedIds, onNavigate]);

  const goNext = useCallback(() => {
    if (index < 0) return;
    if (index < orderedIds.length - 1) {
      onNavigate(orderedIds[index + 1]);
    } else if (pagination?.hasNextPage && !pendingAdvance) {
      setPendingAdvance({ id: orderedIds[index], sawFetch: isFetching });
      pagination.fetchNextPage();
    }
  }, [index, orderedIds, onNavigate, pagination, pendingAdvance, isFetching]);

  return { hasPrev, hasNext, isLoadingNext: pendingAdvance !== null, goPrev, goNext };
}
