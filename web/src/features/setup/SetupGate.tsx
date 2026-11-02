import { useEffect, type ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { consumeTaskDestination, taskDestination, withTaskDestination } from "@/lib/task-continuation";

import { useSetupStatus } from "@/features/settings/use-setup-status";

export function SetupGate({ children }: { children: ReactNode }) {
  const location = useLocation();
  const { data, isError } = useSetupStatus();
  useEffect(() => {
    if (data && location.pathname !== "/") consumeTaskDestination();
  }, [data, location.pathname]);
  if (isError) return <>{children}</>; // fail open — never lock a working app
  if (!data) return <>{children}</>;   // loading: render normally, no flash-gate
  const dismissed = localStorage.getItem("resume-tailor-harness-setup-dismissed") === "1";
  // Browsing a Job, editing evidence/settings, and recording history need no
  // discovery configuration. Action launchers retain their own prerequisites.
  const returning = taskDestination(new URLSearchParams(location.search));
  if (location.pathname === "/" && returning !== "/") return <Navigate to={returning} replace />;
  if (location.pathname === "/" && !data.complete && !dismissed) {
    return <Navigate to={withTaskDestination("/setup", location.pathname + location.search)} replace />;
  }
  return <>{children}</>;
}
