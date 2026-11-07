import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Textarea } from "@/components/ui/textarea";
import { ResetSectionButton } from "../ResetSectionButton";
import { SaveBar } from "../SaveBar";
import { useConfig, useSaveConfig } from "../use-config";
import { useDraft } from "../use-draft";
import { SettingsPage } from "../SettingsPage";

export function StyleGuideSettingsPage() {
  const { data, error, refetch } = useConfig("/api/config/style-guide");
  const save = useSaveConfig("/api/config/style-guide");
  const { draft, setDraft, dirty, reset } = useDraft(data?.content);

  if (draft === null) return <SettingsPage title="Style guide" loading={!error} error={error} onRetry={refetch} />;

  return (
    <SettingsPage title="Style guide" error={error} onRetry={refetch} description="Set the writing rules used when tailoring your resume. Use Markdown for headings and lists." actions={<ResetSectionButton sectionId="style_guide" label="Style guide" onReset={() => setDraft(null)} />}>
      <Field>
        <FieldLabel htmlFor="style-guide">Style guide</FieldLabel>
        <Textarea id="style-guide" value={draft} rows={20}
          className="font-mono text-sm"
          onChange={(e) => setDraft(e.target.value)} />
        <FieldDescription>{draft.length} characters · Markdown</FieldDescription>
      </Field>
      <SaveBar dirty={dirty} saving={save.isPending}
        onSave={() => save.mutate({ content: draft })}
        onDiscard={reset} />
    </SettingsPage>
  );
}
