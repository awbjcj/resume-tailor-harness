import { createContext, useContext, useEffect, useId } from "react";

export type PendingEdit = { dirty: boolean; saving: boolean };
export const UnsavedChangesContext = createContext<
  ((id: string, edit: PendingEdit | null) => void) | null
>(null);

/** Register only edit status; form values and credentials stay in their owner. */
export function useUnsavedChanges(dirty: boolean, saving = false) {
  const register = useContext(UnsavedChangesContext);
  const id = useId();
  useEffect(() => {
    register?.(id, { dirty, saving });
    return () => register?.(id, null);
  }, [register, id, dirty, saving]);
}
