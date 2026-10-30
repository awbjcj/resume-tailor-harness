import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { BoardSkeleton } from "@/components/skeletons";
import { useDeferredComponent } from "@/lib/use-deferred-component";

const load = () => import("./AppLayout").then((module) => ({ default: module.AppLayout }));

export function DeferredAppLayout() {
  const { t } = useTranslation();
  const { Component: Layout, failed, retry, reloadRequired } = useDeferredComponent(true, load);
  if (Layout) return <Layout />;
  return <main className="p-6" aria-busy={!failed}>
    <p role={failed ? "alert" : "status"}>{t(failed ? "deferred.appFailed" : "deferred.loading")}</p>
    {failed ? <Button onClick={retry}>{t(reloadRequired ? "deferred.reload" : "deferred.retry")}</Button> : <BoardSkeleton />}
  </main>;
}
