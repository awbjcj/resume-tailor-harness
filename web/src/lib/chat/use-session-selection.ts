import { useSearchParams } from "react-router-dom";

/** Keep history selection and incoming result links on the same URL state. */
export function useSessionSelection() {
  const [params, setParams] = useSearchParams();
  const selectSession = (sessionId: string | null) => {
    setParams((current) => {
      const next = new URLSearchParams(current);
      if (sessionId) next.set("session", sessionId);
      else next.delete("session");
      return next;
    }, { replace: true });
  };
  return [params.get("session"), selectSession] as const;
}
