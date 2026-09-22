import { useSearchParams } from "react-router-dom";

export type ViewMode = "cards" | "list";

function isViewMode(value: string | null): value is ViewMode {
  return value === "cards" || value === "list";
}

export function useViewMode(storageKey = "board-view"): [ViewMode, (view: ViewMode) => void] {
  const [searchParams, setSearchParams] = useSearchParams();
  const urlView = searchParams.get("view");
  let storedView: string | null = null;
  try {
    storedView = localStorage.getItem(storageKey);
  } catch {
    // URL state still works when browser storage is unavailable.
  }
  const view = isViewMode(urlView) ? urlView : isViewMode(storedView) ? storedView : "cards";

  const setView = (nextView: ViewMode) => {
    try {
      localStorage.setItem(storageKey, nextView);
    } catch {
      // A persistence failure must not prevent changing the current view.
    }
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      next.set("view", nextView);
      return next;
    }, { replace: true });
  };
  return [view, setView];
}
