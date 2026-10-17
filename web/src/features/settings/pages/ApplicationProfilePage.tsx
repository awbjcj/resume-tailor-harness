import { Fragment } from "react";
import { useTranslation } from "react-i18next";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
  FieldLegend,
  FieldSeparator,
  FieldSet,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import type { components } from "@/lib/api/schema";
import { ResetSectionButton } from "../ResetSectionButton";
import { SaveBar } from "../SaveBar";
import { useConfig, useSaveConfig } from "../use-config";
import { useDraft } from "../use-draft";

type Profile = components["schemas"]["ApplicationProfileDoc"];
type AnswerField = {
  key: keyof Profile;
  label: string;
  placeholder?: string;
  multiline?: boolean;
};

function getGroups(): { title: string; description?: string; fields: AnswerField[] }[] {
  return [
    {
      title: "Contact details",
      fields: [
        { key: "fullName", label: "Full name" },
        { key: "preferredName", label: "Preferred name" },
        { key: "email", label: "Email" },
        { key: "phone", label: "Phone" },
        { key: "address", label: "Full address", multiline: true },
        { key: "linkedinUrl", label: "LinkedIn URL" },
        { key: "portfolioUrl", label: "Portfolio URL" },
      ],
    },
    {
      title: "Application preferences",
      fields: [
        { key: "expectedSalary", label: "Expected salary", placeholder: "e.g. USD 120,000–140,000 base per year; negotiable" },
        { key: "workAuthorization", label: "Work authorization", placeholder: "Country and current authorization to work" },
        { key: "sponsorshipNeeded", label: "Sponsorship needed", placeholder: "State whether sponsorship is needed now or in the future" },
        { key: "availability", label: "Start date / notice period" },
        { key: "relocation", label: "Relocation preference" },
        { key: "remotePreference", label: "Remote / hybrid / on-site preference" },
      ],
    },
    {
      title: "Voluntary self-identification",
      description: "Leave unknown answers blank. For voluntary questions, enter your exact answer or “Prefer not to disclose”. Blank answers are never inferred.",
      fields: [
        { key: "pronouns", label: "Pronouns" },
        { key: "gender", label: "Gender" },
        { key: "ethnicity", label: "Race / ethnicity" },
        { key: "veteranStatus", label: "Veteran status" },
        { key: "disabilityStatus", label: "Disability status" },
      ],
    },
    {
      title: "Additional application answers",
      fields: [
        { key: "educationNotes", label: "Education details not in your resume", multiline: true },
        { key: "experienceNotes", label: "Work experience details not in your resume", multiline: true },
        { key: "additionalAnswers", label: "Other application answers", multiline: true },
      ],
    },
  ];
}

export function ApplicationProfilePage() {
  useTranslation();
  const { data, error, refetch } = useConfig("/api/config/application-profile");
  const save = useSaveConfig("/api/config/application-profile");
  const { draft, setDraft, dirty, reset } = useDraft(data);

  if (error) return (
    <Alert variant="destructive">
      <AlertDescription>Could not load application profile.</AlertDescription>
      <Button variant="outline" className="mt-2 w-fit" onClick={() => void refetch()}>Retry</Button>
    </Alert>
  );
  if (!draft) return <Skeleton className="h-64 w-full" />;

  return (
    <div className="flex flex-col gap-6">
      <header className="space-y-1">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h1 className="text-lg font-semibold">Application profile</h1>
          <ResetSectionButton sectionId="application_profile" label="Application profile" onReset={() => setDraft(null)} />
        </div>
        <p className="text-sm text-muted-foreground">
          Optional answers for the English application prompt on each job. Saved resume facts supply your education, experience, skills, and contact details; contact answers here take precedence.
        </p>
      </header>
      <Alert role="note">
        <AlertDescription>
          These details are included when you copy an application prompt and in settings exports. Only save information you want to share with your application assistant.
        </AlertDescription>
      </Alert>
      <FieldGroup>
        {getGroups().map((group, index) => (
          <Fragment key={group.title}>
            {index > 0 && <FieldSeparator />}
            <FieldSet>
              <FieldLegend>{group.title}</FieldLegend>
              {group.description && <FieldDescription>{group.description}</FieldDescription>}
              <div className="grid gap-4 sm:grid-cols-2">
                {group.fields.map((field) => {
                  const id = `application-${field.key}`;
                  const props = {
                    id,
                    value: draft[field.key] ?? "",
                    maxLength: 4000,
                    placeholder: field.placeholder,
                    onChange: (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
                      setDraft({ ...draft, [field.key]: event.target.value }),
                  };
                  return (
                    <Field key={field.key} className={field.multiline ? "min-w-0 sm:col-span-2" : "min-w-0"}>
                      <FieldLabel htmlFor={id}>{field.label}</FieldLabel>
                      {field.multiline ? <Textarea {...props} rows={3} /> : <Input {...props} />}
                    </Field>
                  );
                })}
              </div>
            </FieldSet>
          </Fragment>
        ))}
      </FieldGroup>
      <SaveBar
        dirty={dirty}
        saving={save.isPending}
        onSave={() => save.mutate(draft, { onSuccess: (saved) => setDraft(saved) })}
        onDiscard={reset}
      />
    </div>
  );
}
