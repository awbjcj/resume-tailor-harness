import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { PageHeader } from "@/components/PageHeader";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { ResetSectionButton } from "../ResetSectionButton";
import { SaveBar } from "../SaveBar";
import { useConfig, useSaveConfig } from "../use-config";
import { useDraft } from "../use-draft";

export function StyleGuideSettingsPage() {
  const { data } = useConfig("/api/config/style-guide");
  const save = useSaveConfig("/api/config/style-guide");
  const { draft, setDraft, dirty, reset } = useDraft(data?.content);

  if (draft === null) return <Skeleton className="h-64 w-full" />;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Style guide" actions={<ResetSectionButton sectionId="style_guide" label="Style guide" onReset={() => setDraft(null)} />} />
      <Field>
        <FieldLabel htmlFor="style-guide" className="sr-only">Style guide</FieldLabel>
        <Textarea id="style-guide" value={draft} rows={20}
          className="font-mono text-sm"
          onChange={(e) => setDraft(e.target.value)} />
        <FieldDescription>{draft.length} characters · Markdown</FieldDescription>
      </Field>
      <SaveBar dirty={dirty} saving={save.isPending}
        onSave={() => save.mutate({ content: draft })}
        onDiscard={reset} />
    </div>
  );
}
