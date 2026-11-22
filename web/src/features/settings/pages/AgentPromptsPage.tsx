import { useState } from "react";
import { LockKeyhole } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { ListSearch } from "@/components/ui/list-search";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import promptLabelsZh from "@/i18n/agent-prompt-zh-CN.json";
import { listSearch } from "@/lib/list-search";

import { ResetSectionButton } from "../ResetSectionButton";
import { SettingsPage } from "../SettingsPage";
import { useDraft } from "../use-draft";
import { useUnsavedChanges } from "@/hooks/use-unsaved-changes";
import {
  type AgentPromptItem,
  PROMPTS_KEY,
  usePrompts,
  useSaveGuidance,
} from "../use-prompts";

const STAGES = [
  ["tailoring", "Tailoring"],
  ["review", "Review"],
  ["cover-letter", "Cover letters"],
  ["discovery", "Discovery"],
  ["profile", "Profile"],
  ["interview", "Interview"],
  ["email", "Email"],
] as const;

function instructionsForDisplay(item: AgentPromptItem): string[] {
  if (item.key !== "email-writer") return item.instructions;
  const firstWholeInstruction = item.instructions.findIndex((instruction) => instruction.length !== 1);
  const prefixLength = firstWholeInstruction === -1 ? item.instructions.length : firstWholeInstruction;
  if (prefixLength < 2) return item.instructions;
  return [item.instructions.slice(0, prefixLength).join(""), ...item.instructions.slice(prefixLength)];
}

function PromptRow({ item, visible }: { item: AgentPromptItem; visible: boolean }) {
  const save = useSaveGuidance();
  const { draft, setDraft: setGuidance, dirty } = useDraft(item.guidance ?? "");
  const guidance = draft ?? "";
  useUnsavedChanges(dirty, save.isPending);
  const { i18n } = useTranslation();
  const labels = promptLabelsZh as Record<string, string>;
  const chinese = i18n.resolvedLanguage?.startsWith("zh") ?? false;
  const title = chinese ? labels[item.title] ?? item.title : item.title;
  const description = chinese ? labels[item.description] ?? item.description : item.description;
  const instructions = instructionsForDisplay(item);

  const guidanceId = `guidance-${item.key}`;
  return (
    <AccordionItem value={item.key} hidden={!visible} disabled={!visible}>
      <AccordionTrigger>
        <span className="flex min-w-0 flex-col gap-0.5 pr-3">
          <span>{title}</span>
          <span className="text-xs font-normal text-muted-foreground">
            {description}
          </span>
        </span>
      </AccordionTrigger>
      <AccordionContent className="flex flex-col gap-4">
        <div className="rounded-lg bg-muted/45 p-4 ring-1 ring-foreground/8">
          <ol className="flex list-decimal flex-col gap-2 pl-5 font-mono text-xs leading-relaxed text-muted-foreground">
            {instructions.map((instruction, index) => (
              <li key={`${item.key}-${index}`}>{instruction}</li>
            ))}
          </ol>
        </div>
        {item.editable ? (
          <Field>
            <FieldLabel htmlFor={guidanceId}>Your guidance for {title}</FieldLabel>
            <Textarea
              id={guidanceId}
              maxLength={4000}
              rows={4}
              value={guidance}
              disabled={save.isPending}
              onChange={(event) => setGuidance(event.target.value)}
              placeholder="Steer tone, emphasis, or process without changing facts."
            />
            <div className="flex items-center justify-between gap-3">
              <FieldDescription>{guidance.length.toLocaleString()} / 4,000</FieldDescription>
              <div className="flex items-center gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={!item.guidance || save.isPending}
                  onClick={() => save.mutate({ key: item.key, guidance: "" }, { onSuccess: () => setGuidance("") })}
                >
                  Reset this agent
                </Button>
                <Button
                  size="sm"
                  disabled={save.isPending || guidance === (item.guidance ?? "")}
                  onClick={() => save.mutate({ key: item.key, guidance }, { onSuccess: (saved) => setGuidance(saved.guidance ?? "") })}
                >
                  {save.isPending ? <Spinner data-icon="inline-start" /> : null}
                  Save guidance
                </Button>
              </div>
            </div>
          </Field>
        ) : (
          <Badge variant="secondary" className="w-fit">
            <LockKeyhole data-icon="inline-start" aria-hidden="true" />
            Integrity gate (read-only)
          </Badge>
        )}
      </AccordionContent>
    </AccordionItem>
  );
}

export function AgentPromptsPage() {
  const prompts = usePrompts();
  const queryClient = useQueryClient();
  const { t, i18n } = useTranslation();
  const [search, setSearch] = useState("");
  const [resetVersion, setResetVersion] = useState(0);

  if (prompts.isPending || (!prompts.data && prompts.isError)) return <SettingsPage title="Agent prompts" loading={prompts.isPending} error={prompts.error} onRetry={prompts.refetch} />;

  const items = prompts.data ?? [];

  const matches = listSearch(search);
  const labels: Record<string, string> = i18n.resolvedLanguage?.startsWith("zh") ? promptLabelsZh : {};
  const sections = STAGES.map(([stage, label]) => ({
    stage,
    label,
    items: items.filter((item) => item.stage === stage).map((item) => ({
      item,
      visible: matches(stage, label, item.key, item.title, item.description, labels[item.title], labels[item.description]),
    })),
  }));
  const shown = sections.reduce((total, section) => total + section.items.filter(({ visible }) => visible).length, 0);

  return (
    <SettingsPage title="Agent prompts" error={prompts.error} onRetry={prompts.refetch} description="Customize guidance for each agent. Each agent saves separately; integrity rules remain read-only." actions={<ResetSectionButton sectionId="agent_guidance" label="Agent prompts" onReset={() => {
      queryClient.setQueryData<AgentPromptItem[]>(PROMPTS_KEY, (current) => current?.map((item) => ({ ...item, guidance: null })));
      setResetVersion((version) => version + 1);
    }} />}>
      <p className="text-sm text-muted-foreground">{t("agentPrompts.originalLanguage")}</p>
      <div className="space-y-2">
        <ListSearch value={search} onChange={setSearch} aria-label={t("longLists.searchAgentPrompts")} placeholder={t("longLists.searchAgentPrompts")} className="max-w-lg" />
        <p role="status" className="text-sm text-muted-foreground empty:sr-only">
          {search.trim() ? shown ? t("longLists.results", { shown, total: items.length }) : t("longLists.noMatches") : null}
        </p>
      </div>
      {sections.map(({ stage, label, items }) => {
        if (items.length === 0) return null;
        return (
          <section key={stage} aria-labelledby={`${stage}-heading`} hidden={items.every(({ visible }) => !visible)}>
            <h2 id={`${stage}-heading`} className="text-base font-semibold">
              {label}
            </h2>
            <Accordion multiple className="mt-2 rounded-lg border px-3">
              {items.map(({ item, visible }) => (
                <PromptRow
                  key={`${item.key}-${resetVersion}`}
                  item={item}
                  visible={visible}
                />
              ))}
            </Accordion>
          </section>
        );
      })}
    </SettingsPage>
  );
}
