import { useSearchParams } from "react-router-dom";
import { taskDestination, withTaskDestination } from "@/lib/task-continuation";
import { setupSteps } from "./setup-flow";

export function useSetupContinuation() {
  const [params] = useSearchParams();
  const destination = taskDestination(params);
  const steps = setupSteps(destination);
  const stepPath = (slug: string) => withTaskDestination(`/setup/${slug}`, destination);
  const nextPath = (slug: string) => stepPath(steps[steps.findIndex((step) => step.slug === slug) + 1]?.slug ?? "finish");
  return { destination, steps, stepPath, nextPath };
}
