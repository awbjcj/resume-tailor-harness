import { Sparkles } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { Skeleton } from "@/components/ui/skeleton";
import { buttonVariants } from "@/components/ui/button";
import { SearchConfigForm } from "../forms/SearchConfigForm";
import { ResetSectionButton } from "../ResetSectionButton";
import { SaveBar } from "../SaveBar";
import { useConfig, useSaveConfig } from "../use-config";
import { useDraft } from "../use-draft";

export function SearchSettingsPage() {
  const { data } = useConfig("/api/config/search");
  const save = useSaveConfig("/api/config/search");
  const { draft, setDraft, dirty, reset } = useDraft(data);

  if (!draft) return <Skeleton className="h-64 w-full" />;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Search" actions={<>
          <a
            className={buttonVariants({ variant: "outline", size: "sm" })}
            data-slot="button"
            href="/scout"
          >
            <Sparkles data-icon="inline-start" aria-hidden="true" />
            Ask the Scout
          </a>
          <ResetSectionButton sectionId="search" label="Search" onReset={() => setDraft(null)} />
      </>} />
      <SearchConfigForm value={draft} onChange={setDraft} />
      <SaveBar
        dirty={dirty}
        saving={save.isPending}
        onSave={() => save.mutate(draft, { onSuccess: (saved) => setDraft(saved) })}
        onDiscard={reset}
      />
    </div>
  );
}
