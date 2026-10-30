import { useEffect, useState, type ComponentType } from "react";

/** Retry failed imports and ignore completion after a consumer closes/unmounts. */
export function useDeferredComponent<P extends object>(active: boolean, load: () => Promise<{ default: ComponentType<P> }>) {
  const [Component, setComponent] = useState<ComponentType<P> | null>(null);
  const [failed, setFailed] = useState(false);
  const [reloadRequired, setReloadRequired] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!active || Component) return;
    let current = true;
    load().then(
      (module) => { if (current) setComponent(() => module.default); },
      (error: unknown) => {
        if (!current) return;
        // Browsers cache failed module fetches. Repeating import() cannot
        // reliably recover them; offer an explicit, user-controlled reload.
        setReloadRequired(error instanceof TypeError || (error instanceof Error && /preload|module script|dynamically imported/i.test(error.message)));
        setFailed(true);
      },
    );
    return () => { current = false; };
  }, [active, Component, load, attempt]);
  const retry = () => {
    if (reloadRequired) { window.location.reload(); return; }
    setFailed(false); setAttempt((value) => value + 1);
  };
  return { Component, failed, retry, reloadRequired };
}
