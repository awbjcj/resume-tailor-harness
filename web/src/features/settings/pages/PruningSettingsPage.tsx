import {
  Field,
  FieldContent,
  FieldDescription,
  FieldGroup,
  FieldLabel,
  FieldSet,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import type { paths } from "@/lib/api/schema";
import { ResetSectionButton } from "../ResetSectionButton";
import { SaveBar } from "../SaveBar";
import { useConfig, useSaveConfig } from "../use-config";
import { useDraft } from "../use-draft";
import { SettingsPage, SettingsSection } from "../SettingsPage";

type PruneDoc = paths["/api/config/prune"]["get"]["responses"][200]["content"]["application/json"];

const RULES: { key: "enableRejected" | "enableLowFit" | "enableStale"; label: string; help: string }[] = [
  { key: "enableRejected", label: "Archive rejected jobs",
    help: "Jobs the discovery filter already rejected" },
  { key: "enableLowFit", label: "Archive low-fit jobs",
    help: "Scored jobs below the fit threshold" },
  { key: "enableStale", label: "Archive stale jobs",
    help: "Postings older than the stale window" },
];

export function PruningSettingsPage() {
  const { data, error, refetch } = useConfig("/api/config/prune");
  const save = useSaveConfig("/api/config/prune");
  const { draft, setDraft, dirty, reset } = useDraft(data as PruneDoc | undefined);

  if (!draft) return <SettingsPage title="Pruning" loading={!error} error={error} onRetry={refetch} />;
  const setNum = (key: keyof PruneDoc) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setDraft({ ...draft, [key]: Number(e.target.value || 0) });

  return (
    <SettingsPage title="Pruning" error={error} onRetry={refetch} description="Keep your job list focused with archive rules and a separate retention policy."
      actions={<ResetSectionButton sectionId="prune" label="Pruning" onReset={() => setDraft(null)} />}>
      <FieldSet disabled={save.isPending} className="gap-7">
      <SettingsSection title="Archive rules" description="You can restore archived jobs. Jobs with progress are not archived.">
      <FieldGroup>
        <div className="grid grid-cols-1 gap-4 @lg/settings:grid-cols-2">
          <Field>
            <FieldLabel htmlFor="fitThreshold">Fit threshold</FieldLabel>
            <Input id="fitThreshold" type="number" min={0} max={100} value={draft.fitThreshold}
              onChange={setNum("fitThreshold")} />
            <FieldDescription>Archive scored jobs below this fit score</FieldDescription>
          </Field>
          <Field>
            <FieldLabel htmlFor="staleDays">Stale after (days)</FieldLabel>
            <Input id="staleDays" type="number" min={0} value={draft.staleDays}
              onChange={setNum("staleDays")} />
          </Field>
        </div>
        {RULES.map((rule) => (
          <Field key={rule.key} orientation="horizontal">
            <Switch id={rule.key} checked={draft[rule.key]}
              onCheckedChange={(v: boolean) => setDraft({ ...draft, [rule.key]: v })} />
            <FieldContent>
              <FieldLabel htmlFor={rule.key}>{rule.label}</FieldLabel>
              <FieldDescription>{rule.help}</FieldDescription>
            </FieldContent>
          </Field>
        ))}
      </FieldGroup>
      </SettingsSection>
      <SettingsSection title="Archived job retention" description="This controls permanent deletion after archiving. Deleted jobs cannot be restored.">
        <Field className="max-w-sm">
          <FieldLabel htmlFor="retentionDays">Delete archived after (days)</FieldLabel>
          <Input id="retentionDays" type="number" min={0} value={draft.retentionDays} onChange={setNum("retentionDays")} />
        </Field>
      </SettingsSection>
      </FieldSet>
      <SaveBar dirty={dirty} saving={save.isPending}
        canSave={draft.fitThreshold >= 0 && draft.fitThreshold <= 100 && draft.staleDays >= 0 && draft.retentionDays >= 0}
        onSave={() => save.mutate(draft, { onSuccess: (saved) => setDraft(saved) })} onDiscard={reset} />
    </SettingsPage>
  );
}
