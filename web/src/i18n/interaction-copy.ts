import type { selectionCopyEn } from "./interaction-copy-selection";
import type { redoCopyEn } from "./interaction-copy-redo";
import type { filtersCopyEn } from "./interaction-copy-filters";
import type { resetCopyEn } from "./interaction-copy-reset";
import type { interviewBannerCopyEn } from "./interaction-copy-interviewBanner";
import type { sponsorshipCopyEn } from "./interaction-copy-sponsorship";
import type { notificationsCopyEn } from "./interaction-copy-notifications";
import type { sourcesCopyEn } from "./interaction-copy-sources";

export type InteractionCopy = {
  selection: typeof selectionCopyEn;
  redo: typeof redoCopyEn;
  filters: typeof filtersCopyEn;
  reset: typeof resetCopyEn;
  interviewBanner: typeof interviewBannerCopyEn;
  sponsorship: typeof sponsorshipCopyEn;
  notifications: typeof notificationsCopyEn;
  sources: typeof sourcesCopyEn;
};
