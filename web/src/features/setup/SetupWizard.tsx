import { Check } from "lucide-react";
import { useEffect, useRef } from "react";
import { Navigate, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { useSetupStatus } from "@/features/settings/use-setup-status";
import { consumeTaskDestination } from "@/lib/task-continuation";
import { useSetupContinuation } from "./use-setup-continuation";
import { firstIncompleteStep } from "./setup-flow";
export { STEPS, firstIncompleteStep } from "./setup-flow";
import { cn } from "@/lib/utils";

export function SetupWizard() {
  const { data: status } = useSetupStatus();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const content = useRef<HTMLElement>(null);
  const { destination, steps, stepPath } = useSetupContinuation();

  useEffect(() => { content.current?.focus(); }, [pathname]);

  return (
    <div className="mx-auto flex min-h-svh w-full max-w-2xl flex-col gap-8 px-5 py-10">
      <header className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <div className="min-w-0 flex-1 basis-36 text-[0.68rem] font-semibold uppercase tracking-[0.28em] text-primary [overflow-wrap:anywhere]">
          Résumé Tailor Harness · First-run setup
        </div>
        <Button variant="ghost" size="sm" className="ml-auto h-auto min-h-9 max-w-full py-2 whitespace-normal [overflow-wrap:anywhere]"
          onClick={() => {
            localStorage.setItem("resume-tailor-harness-setup-dismissed", "1");
            consumeTaskDestination();
            navigate(destination);
          }}>
          Exit setup
        </Button>
      </header>
      <nav aria-label="Setup steps" className="-mx-5 flex items-center gap-2 overflow-x-auto px-5 pb-1">
        {steps.map((step, i) => (
          <div key={step.slug} className="flex shrink-0 items-center gap-2">
            {i > 0 && <div className="h-px w-6 shrink-0 bg-border" aria-hidden="true" />}
            <NavLink to={stepPath(step.slug)}
              className={({ isActive }) =>
                cn("flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full border px-3 py-1 text-sm",
                   isActive && "border-primary font-medium")
              }>
              {status && step.done(status) && (
                <Check className="size-3.5 text-primary" aria-hidden="true" />
              )}
              {step.label}
            </NavLink>
          </div>
        ))}
      </nav>
      <main ref={content} tabIndex={-1} className="flex-1 focus:outline-none"><Outlet /></main>
    </div>
  );
}

/** Index route for /setup: resumes at the first incomplete step. */
export function SetupIndexRedirect() {
  const { destination, stepPath } = useSetupContinuation();
  const { data: status, isLoading } = useSetupStatus();
  if (isLoading || !status) return null;
  return <Navigate to={stepPath(firstIncompleteStep(status, destination))} replace />;
}
