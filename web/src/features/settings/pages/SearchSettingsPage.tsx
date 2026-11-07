import { Sparkles } from "lucide-react";
import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { buttonVariants } from "@/components/ui/button";
import { validateTagDrafts } from "@/lib/tag-list-drafts";
import { SearchConfigForm } from "../forms/SearchConfigForm";
import { ResetSectionButton } from "../ResetSectionButton";
import { SaveBar } from "../SaveBar";
import { useConfig, useSaveConfig, useSearchLocationNormalizationPending } from "../use-config";
import { useDraft } from "../use-draft";
import { SettingsPage } from "../SettingsPage";

export function SearchSettingsPage() {
  const { data, error, refetch } = useConfig("/api/config/search");
  const save = useSaveConfig("/api/config/search");
  const normalizing = useSearchLocationNormalizationPending();
  const { draft, setDraft, dirty, reset } = useDraft(data);
  const [formVersion, setFormVersion] = useState(0);
  const fields = useRef<HTMLDivElement>(null);

  if (!draft) return <SettingsPage title="Search" loading={!error} error={error} onRetry={refetch} />;

  return (
    <SettingsPage title="Search" error={error} onRetry={refetch} description="Choose the roles and work preferences used to find and filter jobs." actions={<>
          <Link
            className={buttonVariants({ variant: "outline", size: "sm" })}
            data-slot="button"
            to="/scout"
          >
            <Sparkles data-icon="inline-start" aria-hidden="true" />
            Ask the Scout
          </Link>
        <ResetSectionButton sectionId="search" label="Search" onReset={() => {
          setDraft(null);
          setFormVersion((version) => version + 1);
        }} />
      </>}>
      <div ref={fields}>
      <SearchConfigForm
        key={formVersion}
        value={draft}
        disabled={save.isPending}
        onChange={(update) => setDraft((current) => current && update(current))}
      />
      </div>
      <SaveBar
        dirty={dirty}
        saving={save.isPending}
        canSave={!normalizing && !(draft.yoeMin != null && draft.yoeMax != null && draft.yoeMin > draft.yoeMax)}
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
    </SettingsPage>
  );
}
