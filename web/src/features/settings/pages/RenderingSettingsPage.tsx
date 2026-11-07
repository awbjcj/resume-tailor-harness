import { Eye, Trash2, Upload } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Field,
  FieldContent,
  FieldDescription,
  FieldGroup,
  FieldLabel,
  FieldLegend,
  FieldSet,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { QueryFeedback } from "@/components/QueryFeedback";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import type { paths } from "@/lib/api/schema";

import { ResetSectionButton } from "../ResetSectionButton";
import { SaveBar } from "../SaveBar";
import { useConfig, useSaveConfig } from "../use-config";
import { useDraft } from "../use-draft";
import { SettingsPage } from "../SettingsPage";
import {
  openTemplatePreview,
  useDeleteTemplate,
  useRenderTemplates,
  useUploadTemplate,
} from "../use-render-templates";

type RenderDoc =
  paths["/api/config/render"]["get"]["responses"][200]["content"]["application/json"];

export function RenderingSettingsPage() {
  const { data, error, refetch } = useConfig("/api/config/render");
  const save = useSaveConfig("/api/config/render");
  const templates = useRenderTemplates();
  const upload = useUploadTemplate();
  const remove = useDeleteTemplate();
  const { draft, setDraft, dirty, reset } = useDraft(data as RenderDoc | undefined);

  if (!draft) return <SettingsPage title="Rendering" loading={!error} error={error} onRetry={refetch} />;

  return (
    <SettingsPage title="Rendering" error={error} onRetry={refetch} description="Choose a resume layout and page length. Template uploads apply immediately; save layout options together below." actions={
        <ResetSectionButton
          sectionId="render"
          onReset={() => setDraft(null)}
          label="Rendering options"
          buttonLabel="Reset options"
          note="Custom uploaded templates are kept. Reset them separately below."
        />
      }>

      <FieldSet>
        <FieldLegend>Resume template</FieldLegend>
        {templates.isError || templates.isPending ? (
          <QueryFeedback error={templates.error} onRetry={templates.refetch} loadingLabel="Loading rendering settings" />
        ) : (
          <RadioGroup
            value={draft.template}
            disabled={save.isPending}
            onValueChange={(template) => setDraft({ ...draft, template })}
            className="grid grid-cols-1 gap-3 @2xl/settings:grid-cols-2"
          >
            {templates.data.map((item) => {
              const selected = draft.template === item.id;
              return (
                <Card
                  key={item.id}
                  className={cn("cursor-pointer", selected && "ring-2 ring-primary")}
                  onClick={(event) => {
                    if (save.isPending) return;
                    if (event.target instanceof Element && event.target.closest("button")) {
                      return;
                    }
                    setDraft({ ...draft, template: item.id });
                  }}
                >
                  <CardHeader>
                    <div className="flex items-start gap-3">
                      <RadioGroupItem
                        value={item.id}
                        aria-label={`Use ${item.title} template`}
                      />
                      <div className="flex min-w-0 flex-col gap-1">
                        <CardTitle>{item.title}</CardTitle>
                        <CardDescription>{item.description}</CardDescription>
                      </div>
                    </div>
                    <CardAction>
                      {item.kind === "custom" ? (
                        <Badge variant="secondary">Custom</Badge>
                      ) : (
                        <Badge variant="outline">Bundled</Badge>
                      )}
                    </CardAction>
                  </CardHeader>
                  <CardContent className="flex items-center gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => void openTemplatePreview(item.id)}
                    >
                      <Eye data-icon="inline-start" aria-hidden="true" />
                      Preview
                    </Button>
                    {item.kind === "custom" ? (
                      <Button
                        size="sm"
                        variant="ghost"
                        aria-label={`Delete ${item.title} template`}
                        disabled={remove.isPending}
                        onClick={() => remove.mutate(item.id.replace(/^custom:/, ""))}
                      >
                        <Trash2 data-icon="inline-start" aria-hidden="true" />
                        Delete
                      </Button>
                    ) : null}
                  </CardContent>
                </Card>
              );
            })}
          </RadioGroup>
        )}
      </FieldSet>

      <FieldGroup>
        <Field data-invalid={Boolean(upload.error)}>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <FieldLabel htmlFor="template-upload">
              <Upload aria-hidden="true" />
              Upload Typst template
            </FieldLabel>
            <ResetSectionButton
              sectionId="templates"
              label="Custom resume templates"
              buttonLabel="Reset custom templates"
              note="This deletes every custom template you uploaded; the bundled templates remain."
            />
          </div>
          <Input
            id="template-upload"
            type="file"
            accept=".typ"
            aria-invalid={Boolean(upload.error)}
            disabled={upload.isPending}
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) upload.mutate(file);
            }}
          />
          <FieldDescription>
            Your template must read sys.inputs.data (resume JSON) and sys.inputs.zoom.
          </FieldDescription>
          {upload.error ? (
            <p role="alert" className="whitespace-pre-wrap text-sm text-destructive">
              {upload.error.message}
            </p>
          ) : null}
        </Field>

        <Field orientation="horizontal">
          <Switch
            id="fit-one-page"
            disabled={save.isPending}
            aria-label="Fit resume to one page"
            checked={draft.fitOnePage}
            onCheckedChange={(fitOnePage: boolean) =>
              setDraft({ ...draft, fitOnePage })}
          />
          <FieldContent>
            <FieldLabel htmlFor="fit-one-page">Fit resume to one page</FieldLabel>
            <FieldDescription>
              Keep a concise summary and relevant optional sections. Turn this off to
              allow one page or two nearly full pages. For bundled layouts, body
              text and spacing adjust automatically; body text stays between 10
              and 12pt. Revise the content if it still cannot fit cleanly.
            </FieldDescription>
          </FieldContent>
        </Field>
      </FieldGroup>

      <p className="text-sm text-muted-foreground">
        Rendered PDFs are stored in your workspace and downloaded from each job&apos;s page.
      </p>
      <SaveBar
        dirty={dirty}
        saving={save.isPending}
        onSave={() => save.mutate(draft)}
        onDiscard={reset}
      />
    </SettingsPage>
  );
}
