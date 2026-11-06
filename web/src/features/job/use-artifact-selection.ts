import { useCallback, useMemo, useState } from "react";

/**
 * Checkbox selection for a list of deletable artifacts.
 *
 * Drop a selection when its row becomes unavailable. If the row becomes
 * deletable again, the user can explicitly select it again.
 */
export function useArtifactSelection(deletableIds: readonly number[]) {
  const [raw, setRaw] = useState<ReadonlySet<number>>(() => new Set());

  const selectedIds = useMemo(
    () => deletableIds.filter((id) => raw.has(id)),
    [deletableIds, raw],
  );
  if (selectedIds.length !== raw.size) setRaw(new Set(selectedIds));

  const toggle = useCallback((id: number) => {
    setRaw((current) => {
      const next = new Set(current);
      if (!next.delete(id)) next.add(id);
      return next;
    });
  }, []);

  const clear = useCallback(() => setRaw(new Set()), []);

  const toggleAll = useCallback(() => {
    setRaw((current) =>
      deletableIds.every((id) => current.has(id))
        ? new Set()
        : new Set(deletableIds),
    );
  }, [deletableIds]);

  return {
    selectedIds,
    isSelected: (id: number) => raw.has(id),
    allSelected:
      deletableIds.length > 0 && selectedIds.length === deletableIds.length,
    toggle,
    toggleAll,
    clear,
  };
}
