import { ArrowUpRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";

export function RunResultLink({ item }: { item: { resultHref?: string | null; resultAvailable?: boolean } }) {
  const { t } = useTranslation();
  if (!item.resultHref) return null;
  return <Button size="xs" variant="outline" render={<Link to={item.resultHref} />}>
    <ArrowUpRight aria-hidden="true" />
    {t(item.resultAvailable ? "runHistory.openResult" : "runHistory.openWorkspace")}
  </Button>;
}
