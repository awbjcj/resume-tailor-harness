import { useTranslation } from "react-i18next";
import "@/i18n/roadmap-copy";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import type { SuggestionTarget } from "./aggregate";
import { SuggestionPanel } from "./SuggestionPanel";
import { useGenerateSuggestion, useSuggestion } from "./use-suggestion";

export function DomainRoadmapDialog({ target, onClose }: { target: SuggestionTarget | null; onClose: () => void }) {
  const { t } = useTranslation();
  const query = useSuggestion("domain", target?.key ?? null, target !== null);
  const { generate, generating } = useGenerateSuggestion();
  return <Dialog open={target !== null} onOpenChange={(open) => !open && onClose()}>
    <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-3xl [overflow-wrap:anywhere]">
      <DialogHeader>
        <DialogTitle>{target?.label ?? target?.key}</DialogTitle>
        <DialogDescription>{t("roadmaps.domainDescription")}</DialogDescription>
      </DialogHeader>
      <SuggestionPanel envelope={query.data} isLoading={query.isLoading} isError={query.isError}
        onRetry={() => void query.refetch()} onGenerate={() => target && void generate("domain", target.key)} generating={generating} />
    </DialogContent>
  </Dialog>;
}
