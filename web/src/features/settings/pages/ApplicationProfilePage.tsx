import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import type { components } from "@/lib/api/schema";
import { ResetSectionButton } from "../ResetSectionButton";
import { SaveBar } from "../SaveBar";
import { useConfig, useSaveConfig } from "../use-config";
import { useDraft } from "../use-draft";

type Profile = components["schemas"]["ApplicationProfileDoc"];
type AnswerField = { key: keyof Profile; label: string; placeholder?: string; multiline?: boolean };

function getGroups(): { title: string; fields: AnswerField[] }[] {
  return [
  { title: "Contact details", fields: [
    { key: "fullName", label: "Full name" },
    { key: "preferredName", label: "Preferred name" },
    { key: "email", label: "Email" },
    { key: "phone", label: "Phone" },
    { key: "address", label: "Full address", multiline: true },
    { key: "linkedinUrl", label: "LinkedIn URL" },
    { key: "portfolioUrl", label: "Portfolio URL" },
  ] },
  { title: "Application preferences", fields: [
    { key: "expectedSalary", label: "Expected salary", placeholder: "e.g. USD 120,000–140,000 base per year; negotiable" },
    { key: "workAuthorization", label: "Work authorization", placeholder: "Country and current authorization to work" },
    { key: "sponsorshipNeeded", label: "Sponsorship needed", placeholder: "State whether sponsorship is needed now or in the future" },
    { key: "availability", label: "Start date / notice period" },
    { key: "relocation", label: "Relocation preference" },
    { key: "remotePreference", label: "Remote / hybrid / on-site preference" },
  ] },
  { title: "Voluntary self-identification", fields: [
    { key: "pronouns", label: "Pronouns" },
    { key: "gender", label: "Gender" },
    { key: "ethnicity", label: "Race / ethnicity" },
    { key: "veteranStatus", label: "Veteran status" },
    { key: "disabilityStatus", label: "Disability status" },
  ] },
  { title: "Additional application answers", fields: [
    { key: "educationNotes", label: "Education details not in your resume", multiline: true },
    { key: "experienceNotes", label: "Work experience details not in your resume", multiline: true },
    { key: "additionalAnswers", label: "Other application answers", multiline: true },
  ] },
  ];
}

export function ApplicationProfilePage() {
  useTranslation();
  const { data, error, refetch } = useConfig("/api/config/application-profile");
  const save = useSaveConfig("/api/config/application-profile");
  const { draft, setDraft, dirty, reset } = useDraft(data);

  if (error) return <div role="alert"><p>Could not load application profile.</p><Button onClick={() => void refetch()}>Retry</Button></div>;
  if (!draft) return <Skeleton className="h-64 w-full" />;

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="max-w-2xl space-y-2">
          <h1 className="text-lg font-semibold">Application profile</h1>
          <p className="text-sm text-muted-foreground">
            Optional answers for the English application prompt on each job. Saved resume facts supply your education, experience, skills, and contact details; contact answers here take precedence.
          </p>
          <p className="text-sm text-muted-foreground">
            Leave unknown answers blank. For voluntary questions, enter your exact answer or “Prefer not to disclose”. Blank answers are never inferred.
          </p>
          <p className="text-sm text-muted-foreground">
            These details are included when you copy an application prompt and in settings exports. Only save information you want to share with your application assistant.
          </p>
        </div>
        <ResetSectionButton sectionId="application_profile" label="Application profile" onReset={() => setDraft(null)} />
      </header>
      {getGroups().map((group) => (
        <fieldset key={group.title} className="rounded-xl border p-4 sm:p-5">
          <legend className="px-2 text-sm font-semibold">{group.title}</legend>
          <div className="grid gap-4 sm:grid-cols-2">
            {group.fields.map((field) => {
              const id = `application-${field.key}`;
              const props = {
                id, value: draft[field.key] ?? "", maxLength: 4000,
                placeholder: field.placeholder,
                onChange: (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setDraft({ ...draft, [field.key]: event.target.value }),
              };
              return (
                <div key={field.key} className={field.multiline ? "space-y-2 sm:col-span-2" : "space-y-2"}>
                  <Label htmlFor={id}>{field.label}</Label>
                  {field.multiline ? <Textarea {...props} rows={3} /> : <Input {...props} />}
                </div>
              );
            })}
          </div>
        </fieldset>
      ))}
      <SaveBar dirty={dirty} saving={save.isPending}
        onSave={() => save.mutate(draft, { onSuccess: (saved) => setDraft(saved) })}
        onDiscard={reset} />
    </div>
  );
}
