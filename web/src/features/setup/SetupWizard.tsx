import { Check } from "lucide-react";
import { Navigate, NavLink, Outlet, useNavigate } from "react-router-dom";

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
  const { destination, steps, stepPath } = useSetupContinuation();
  return (
    <div className="mx-auto flex min-h-svh w-full max-w-2xl flex-col gap-8 px-5 py-10">
      <header className="flex items-center gap-3">
        <div className="text-[0.68rem] font-semibold uppercase tracking-[0.28em] text-primary">
          Résumé Tailor Harness · First-run setup
        </div>
        <Button variant="ghost" size="sm" className="ml-auto"
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
      <main className="flex-1"><Outlet /></main>
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
