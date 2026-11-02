import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Navigate, useLocation } from "react-router-dom";

import { Button } from "@/components/ui/button";
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyTitle,
} from "@/components/ui/empty";
import { Skeleton } from "@/components/ui/skeleton";
import { api, unwrap } from "@/lib/api/client";
import { taskDestinationForLocation, withTaskDestination } from "@/lib/task-continuation";

export function useMe() {
  return useQuery({
    queryKey: ["auth", "me"],
    queryFn: () => unwrap(api.GET("/api/auth/me")),
    staleTime: 60_000,
  });
}

export function AuthGate({ children }: { children: ReactNode }) {
  const location = useLocation();
  const requested = taskDestinationForLocation(location.pathname, location.search, location.hash);
  const me = useMe();
  if (me.isPending) {
    return (
      <div
        className="flex min-h-dvh items-center justify-center p-6"
        aria-label="Checking session"
        aria-busy="true"
        role="status"
      >
        <Skeleton className="h-40 w-full max-w-sm" />
      </div>
    );
  }
  if (me.isError) {
    return (
      <main className="flex min-h-dvh items-center justify-center p-6">
        <Empty>
          <EmptyHeader>
            <EmptyTitle>Could not verify your session</EmptyTitle>
            <EmptyDescription>{me.error.message}</EmptyDescription>
          </EmptyHeader>
          <EmptyContent>
            <Button variant="outline" onClick={() => void me.refetch()}>Retry</Button>
          </EmptyContent>
        </Empty>
      </main>
    );
  }
  if (me.data.authRequired && !me.data.username) {
    return <Navigate to={withTaskDestination("/login", requested)} replace />;
  }
  if (me.data.needsEmail) {
    return <Navigate to={withTaskDestination("/complete-profile", requested)} replace />;
  }
  return <>{children}</>;
}
