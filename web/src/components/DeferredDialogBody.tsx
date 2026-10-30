import type { ComponentType } from "react";
import { useTranslation } from "react-i18next";
import { useDeferredComponent } from "@/lib/use-deferred-component";

import { Button } from "@/components/ui/button";
import { DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";

/** Keep the trigger and loaded form mounted, so closing never discards a draft. */
export function DeferredDialogBody<P extends object>({
  active, title, load, bodyProps,
}: {
  active: boolean;
  title: string;
  load: () => Promise<{ default: ComponentType<P> }>;
  bodyProps: P;
}) {
  const { t } = useTranslation();
  const { Component: Body, failed, retry, reloadRequired } = useDeferredComponent(active, load);

  if (Body) return <Body {...bodyProps} />;
  if (!active) return null;
  return <DialogContent>
    <DialogHeader>
      <DialogTitle>{title}</DialogTitle>
      <DialogDescription role={failed ? "alert" : "status"}>
        {t(failed ? "deferred.failed" : "deferred.loading")}
      </DialogDescription>
    </DialogHeader>
    {failed && <Button onClick={retry}>
      {t(reloadRequired ? "deferred.reload" : "deferred.retry")}
    </Button>}
  </DialogContent>;
}
