import { ArrowUpRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { buttonVariants } from "@/components/ui/button";

export function RunResultLink({ item }: { item: { resultHref?: string | null; resultAvailable?: boolean } }) {
  const { t } = useTranslation();
  if (!item.resultHref) return null;
  return <Link to={item.resultHref} className={buttonVariants({ size: "xs", variant: "outline" })}>
    <ArrowUpRight aria-hidden="true" />
    {t(item.resultAvailable ? "runHistory.openResult" : "runHistory.openWorkspace")}
  </Link>;
}
