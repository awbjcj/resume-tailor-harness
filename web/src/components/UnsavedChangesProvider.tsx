import { useCallback, useState, type ReactNode } from "react";
import { useBeforeUnload, useBlocker } from "react-router-dom";

import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { UnsavedChangesContext, type PendingEdit } from "@/hooks/use-unsaved-changes";

function profileTabOnly(currentPath: string, nextPath: string, currentSearch: string, nextSearch: string) {
  if (currentPath !== "/profile" || nextPath !== currentPath) return false;
  const current = new URLSearchParams(currentSearch);
  const next = new URLSearchParams(nextSearch);
  if (current.get("tab") === next.get("tab")) return false;
  current.delete("tab");
  next.delete("tab");
  return current.toString() === next.toString();
}

/** One blocker for the workspace, including pages with several independent editors. */
export function UnsavedChangesProvider({ children }: { children: ReactNode }) {
  const [edits, setEdits] = useState<Record<string, PendingEdit>>({});
  const register = useCallback((id: string, edit: PendingEdit | null) => {
    setEdits((current) => {
      if (!edit?.dirty && !current[id]) return current;
      const next = { ...current };
      if (edit?.dirty) next[id] = edit;
      else delete next[id];
      return next;
    });
  }, []);
  const dirty = Object.values(edits).some((edit) => edit.dirty);
  const saving = Object.values(edits).some((edit) => edit.saving);
  const blocker = useBlocker(({ currentLocation, nextLocation }) => dirty && (
    currentLocation.pathname !== nextLocation.pathname || (
      currentLocation.search !== nextLocation.search && !profileTabOnly(
        currentLocation.pathname, nextLocation.pathname, currentLocation.search, nextLocation.search,
      )
    )
  ));
  useBeforeUnload(useCallback((event) => {
    if (!dirty) return;
    event.preventDefault();
    event.returnValue = "";
  }, [dirty]));

  return (
    <UnsavedChangesContext.Provider value={register}>
      {children}
      <AlertDialog open={blocker.state === "blocked"} onOpenChange={(open) => {
        if (!open && blocker.state === "blocked") blocker.reset();
      }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Leave with unsaved changes?</AlertDialogTitle>
            <AlertDialogDescription>
              Your edits have not been saved. Keep editing to save them, or discard them and leave this page.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep editing</AlertDialogCancel>
            <AlertDialogAction disabled={saving} onClick={() => {
              if (blocker.state === "blocked") blocker.proceed();
            }}>Discard and leave</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </UnsavedChangesContext.Provider>
  );
}
