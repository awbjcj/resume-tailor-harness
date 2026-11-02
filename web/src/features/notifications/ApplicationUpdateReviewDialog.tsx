import { useState } from "react";
import "@/i18n/application-updates";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useDeferredComponent } from "@/lib/use-deferred-component";
import type { NotificationItem } from "./use-notifications";

const CAPTURABLE_STATUS_VALUES = new Set(["submitted", "interview", "offer", "rejected", "closed"]);
const loadReview = () => import("./ApplicationUpdateReviewBody").then((module) => ({
  default: module.ApplicationUpdateReviewBody,
}));

export function ApplicationUpdateReviewDialog({ item }: { item: NotificationItem }) {
  const { t } = useTranslation();
  // Freeze before loading the form. Background sync cannot replace the
  // evidence or revision the user chose while the module is still arriving.
  const [reviewed, setReviewed] = useState<NotificationItem | null>(null);
  const { Component: ReviewBody, failed, retry, reloadRequired } = useDeferredComponent(reviewed !== null, loadReview);

  if (!CAPTURABLE_STATUS_VALUES.has(item.proposedStatus) || item.jobId == null) return null;

  return (
    <>
      <Button size="sm" variant="outline" onClick={() => setReviewed({ ...item })}>
        {t("applicationUpdates.addToTimeline")}
      </Button>
      {reviewed && (ReviewBody ? (
        <ReviewBody item={reviewed} onClose={() => setReviewed(null)} />
      ) : (
        <Dialog open onOpenChange={(open) => !open && setReviewed(null)}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{t("applicationUpdates.reviewTitle")}</DialogTitle>
              <DialogDescription role={failed ? "alert" : "status"}>
                {t(failed ? "deferred.failed" : "deferred.loading")}
              </DialogDescription>
            </DialogHeader>
            {failed && <Button onClick={retry}>
              {t(reloadRequired ? "deferred.reload" : "deferred.retry")}
            </Button>}
          </DialogContent>
        </Dialog>
      ))}
    </>
  );
}
