import { Sparkles } from "lucide-react";
import { useRef, useState } from "react";
import { PageHeader } from "@/components/PageHeader";
import { Skeleton } from "@/components/ui/skeleton";
import { buttonVariants } from "@/components/ui/button";
import { validateTagDrafts } from "@/lib/tag-list-drafts";
import { SearchConfigForm } from "../forms/SearchConfigForm";
import { ResetSectionButton } from "../ResetSectionButton";
import { SaveBar } from "../SaveBar";
import { useConfig, useSaveConfig, useSearchLocationNormalizationPending } from "../use-config";
import { useDraft } from "../use-draft";

export function SearchSettingsPage() {
  const { data } = useConfig("/api/config/search");
  const save = useSaveConfig("/api/config/search");
  const normalizing = useSearchLocationNormalizationPending();
  const { draft, setDraft, dirty, reset } = useDraft(data);
  const [formVersion, setFormVersion] = useState(0);
  const fields = useRef<HTMLDivElement>(null);

  if (!draft) return <Skeleton className="h-64 w-full" />;

  return (
    <div ref={fields} className="flex flex-col gap-6">
      <PageHeader title="Search" actions={<>
          <a
            className={buttonVariants({ variant: "outline", size: "sm" })}
            data-slot="button"
            href="/scout"
          >
            <Sparkles data-icon="inline-start" aria-hidden="true" />
            Ask the Scout
          </a>
        <ResetSectionButton sectionId="search" label="Search" onReset={() => {
          setDraft(null);
          setFormVersion((version) => version + 1);
        }} />
      </>} />
      <SearchConfigForm
        key={formVersion}
        value={draft}
        disabled={save.isPending}
        onChange={(update) => setDraft((current) => current && update(current))}
      />
      <SaveBar
        dirty={dirty}
        saving={save.isPending}
        canSave={!normalizing}
        onSave={() => {
          if (validateTagDrafts(fields.current)) {
            save.mutate(draft, { onSuccess: (saved) => setDraft(saved) });
          }
        }}
        onDiscard={() => {
          reset();
          setFormVersion((version) => version + 1);
        }}
      />
    </div>
  );
}
