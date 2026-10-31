import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldLabel, FieldLegend, FieldSet } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import type { components } from "@/lib/api/schema";

type Profile = components["schemas"]["ApplicationProfileDoc"];
type Name = components["schemas"]["ApplicationName"];
type Address = components["schemas"]["MailingAddress"];
type Email = components["schemas"]["AlternateEmail"];
type Eligibility = components["schemas"]["WorkEligibility"];
type Experience = components["schemas"]["ExperienceRange"];
type Employer = components["schemas"]["EmployerAnswer"];

type AnswerField<T> = {
  key: Extract<keyof T, string>;
  label: string;
  type?: "text" | "date" | "email" | "number" | "boolean" | "textarea" | "select";
  required?: boolean;
  options?: { value: string; label: string }[];
};

function AnswerFields<T extends object>({ value, fields, prefix, onChange }: {
  value: T; fields: AnswerField<T>[]; prefix: string; onChange: (next: T) => void;
}) {
  return <div className="grid gap-4 sm:grid-cols-2">
    {fields.map((field) => {
      const id = `${prefix}-${field.key}`;
      const raw = value[field.key];
      const update = (next: string | number | boolean | null) => onChange({ ...value, [field.key]: next });
      const props = {
        id, required: field.required, value: raw == null ? "" : String(raw),
        onChange: (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
          const next = event.target.value;
          update(field.type === "number" ? (next === "" ? null : Number(next))
            : field.type === "date" && !next ? null : next);
        },
      };
      return <Field key={field.key} className={field.type === "textarea" ? "min-w-0 sm:col-span-2" : "min-w-0"}>
        <FieldLabel htmlFor={id}>{field.label}{field.required ? " *" : ""}</FieldLabel>
        {field.type === "boolean" || field.type === "select" ? (
          <select id={id} required={field.required}
            className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-ring"
            value={field.type === "boolean" ? (raw == null ? "unknown" : raw ? "yes" : "no") : String(raw ?? "unknown")}
            onChange={(event) => update(field.type === "boolean"
              ? event.target.value === "unknown" ? null : event.target.value === "yes"
              : event.target.value)}>
            {field.type === "boolean" ? <>
              <option value="unknown">Unknown</option><option value="yes">Yes</option><option value="no">No</option>
            </> : field.options?.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
        ) : field.type === "textarea" ? <Textarea {...props} rows={3} maxLength={4000} /> : (
          <Input {...props} type={field.type ?? "text"} maxLength={field.type === "email" ? 254 : 4000}
            min={field.type === "number" ? 0 : undefined} max={field.type === "number" ? 100 : undefined}
            step={field.type === "number" ? "any" : undefined} />
        )}
      </Field>;
    })}
  </div>;
}

function Section({ title, description, children }: { title: string; description?: string; children: ReactNode }) {
  return <FieldSet className="border-t pt-6">
    <FieldLegend>{title}</FieldLegend>
    {description && <FieldDescription>{description}</FieldDescription>}
    {children}
  </FieldSet>;
}

function Records<T extends object>({ title, description, items, fields, create, addLabel, removeLabel, onChange, prefix }: {
  title: string; description: string; items: T[]; fields: AnswerField<T>[]; create: () => T;
  addLabel: string; removeLabel: string; onChange: (items: T[]) => void; prefix: string;
}) {
  return <Section title={title} description={description}>
    {items.map((item, index) => <fieldset key={index} className="min-w-0 space-y-4 rounded-lg border p-4">
      <legend className="px-1 text-sm font-medium">{title} {index + 1}</legend>
      <AnswerFields value={item} fields={fields} prefix={`${prefix}-${index}`}
        onChange={(next) => onChange(items.map((old, at) => at === index ? next : old))} />
      <Button type="button" variant="outline" size="sm" onClick={() => onChange(items.filter((_, at) => at !== index))}>
        {removeLabel}
      </Button>
    </fieldset>)}
    <Button type="button" variant="outline" className="w-fit" disabled={items.length >= 100}
      onClick={() => onChange([...items, create()])}>{addLabel}</Button>
  </Section>;
}

const nameFields: AnswerField<Name>[] = [
  { key: "givenName", label: "Given name" }, { key: "middleName", label: "Middle name" },
  { key: "familyName", label: "Family name" }, { key: "suffix", label: "Name suffix" },
];
const emptyName: Name = { givenName: "", middleName: "", familyName: "", suffix: "" };
const emptyAddress: Address = { line1: "", line2: "", city: "", region: "", postalCode: "", country: "" };
const addressFields: AnswerField<Address>[] = [
  { key: "line1", label: "Address line 1" }, { key: "line2", label: "Address line 2" },
  { key: "city", label: "City" }, { key: "region", label: "State / province / region" },
  { key: "postalCode", label: "Postal code" }, { key: "country", label: "Address country" },
];
const emailFields: AnswerField<Email>[] = [
  { key: "email", label: "Alternate email", type: "email", required: true },
  { key: "employer", label: "Employer (blank means all employers)" },
  { key: "requisition", label: "Requisition / role ID" }, { key: "country", label: "Applicable country" },
  { key: "permitted", label: "May use for applications", type: "boolean" },
  { key: "confirmedOn", label: "Confirmation date", type: "date", required: true },
];
const eligibilityFields: AnswerField<Eligibility>[] = [
  { key: "country", label: "Country", required: true },
  { key: "immigrationStatus", label: "Immigration status" },
  { key: "authorizedToWork", label: "Legally authorized to work", type: "boolean" },
  { key: "sponsorshipNow", label: "Needs sponsorship now", type: "boolean" },
  { key: "sponsorshipFuture", label: "Needs sponsorship in the future", type: "boolean" },
  { key: "canVerifyAuthorization", label: "Can verify legal right to work", type: "boolean" },
  { key: "currentlyOnOpt", label: "Currently on OPT", type: "boolean" },
  { key: "stemOptExtensionEligible", label: "Eligible for a STEM OPT extension", type: "boolean" },
  { key: "confirmedOn", label: "Confirmation date", type: "date", required: true },
];
const experienceFields: AnswerField<Experience>[] = [
  { key: "specialty", label: "Area of experience", required: true },
  { key: "minimumYears", label: "Minimum years", type: "number" },
  { key: "maximumYears", label: "Maximum years", type: "number" },
  { key: "confirmedOn", label: "Confirmation date", type: "date", required: true },
];
const employerFields: AnswerField<Employer>[] = [
  { key: "employer", label: "Employer", required: true },
  { key: "requisition", label: "Requisition / role ID" },
  { key: "country", label: "Applicable country" },
  { key: "category", label: "Answer category", type: "select", options: [
    { value: "general", label: "General screening" }, { value: "referral", label: "Referral source" },
    { value: "employment", label: "Employment history" }, { value: "contractor", label: "Contractor history" },
    { value: "relationship", label: "Employer relationships" }, { value: "previous_application", label: "Application history" },
    { value: "degree_category", label: "Degree dropdown mapping" }, { value: "role_requirement", label: "Role requirements" },
  ] },
  { key: "question", label: "Exact question or degree option details", type: "textarea", required: true },
  { key: "answer", label: "Confirmed answer (blank means unknown)", type: "textarea" },
  { key: "timeframe", label: "Applicable timeframe" },
  { key: "confirmedOn", label: "Confirmation date", type: "date", required: true },
  { key: "validUntil", label: "Valid until (optional)", type: "date" },
];

export function StructuredApplicationProfile({ profile, onChange }: {
  profile: Profile; onChange: (changes: Partial<Profile>) => void;
}) {
  return <>
    <Section title="Names and mailing address"
      description="Enter each part of your name and address as it should appear on applications. Blank fields stay unknown; your existing contact notes are kept.">
      <fieldset className="space-y-4"><legend className="mb-3 text-sm font-medium">Legal name</legend>
        <AnswerFields prefix="legal-name" value={profile.legalName ?? emptyName} fields={nameFields} onChange={(legalName) => onChange({ legalName })} />
      </fieldset>
      <fieldset className="space-y-4"><legend className="mb-3 text-sm font-medium">Preferred name</legend>
        <AnswerFields prefix="preferred-name" value={profile.preferredNameParts ?? emptyName} fields={nameFields} onChange={(preferredNameParts) => onChange({ preferredNameParts })} />
      </fieldset>
      <AnswerFields prefix="mailing-address" value={profile.mailingAddress ?? emptyAddress} fields={addressFields} onChange={(mailingAddress) => onChange({ mailingAddress })} />
    </Section>
    <Records<Email> title="Alternate application emails" prefix="alternate-email" items={profile.alternateEmails ?? []} fields={emailFields}
      description="Keep your primary email above. Use an alternate only with explicit permission and when its employer, requisition, and country limits match the application."
      addLabel="Add alternate email" removeLabel="Remove alternate email"
      create={() => ({ email: "", employer: "", requisition: "", country: "", permitted: null, confirmedOn: "" })}
      onChange={(alternateEmails) => onChange({ alternateEmails })} />
    <Records<Eligibility> title="Work eligibility by country" prefix="eligibility" items={profile.workEligibility ?? []} fields={eligibilityFields}
      description="Record each country separately. Unknown does not mean No. Answer immigration status, work authorization, sponsorship, OPT, and STEM eligibility separately."
      addLabel="Add country eligibility" removeLabel="Remove country eligibility"
      create={() => ({ country: "", immigrationStatus: "", confirmedOn: "" })} onChange={(workEligibility) => onChange({ workEligibility })} />
    <Records<Experience> title="Experience by specialty" prefix="experience-range" items={profile.experienceRanges ?? []} fields={experienceFields}
      description="Enter your own experience range for each specialty. Fill in both the minimum and maximum, or leave both blank. A range cannot stand in for an exact number of years and does not increase automatically over time."
      addLabel="Add experience range" removeLabel="Remove experience range"
      create={() => ({ specialty: "", minimumYears: null, maximumYears: null, confirmedOn: "" })}
      onChange={(experienceRanges) => onChange({ experienceRanges })} />
    <Section title="Application defaults"
      description="Sex and gender are separate, optional disclosures. The AI preference covers optional candidate matching only. Confirm agreements and submission separately for each application.">
      <AnswerFields prefix="application-default" value={profile} fields={[
        { key: "sex", label: "Sex (optional self-identification)" },
        { key: "sexConfirmedOn", label: "Sex answer confirmation date", type: "date" },
        { key: "aiMatchingPreference", label: "AI-assisted candidate matching", type: "select", options: [
          { value: "unknown", label: "Unknown" }, { value: "opt_in", label: "Opt in" },
          { value: "opt_out", label: "Opt out" }, { value: "ask", label: "Ask each time" },
        ] },
        { key: "aiMatchingConfirmedOn", label: "AI matching preference confirmation date", type: "date" },
      ]} onChange={onChange} />
    </Section>
    <Records<Employer> title="Employer answers" prefix="employer-answer" items={profile.employerAnswers ?? []} fields={employerFields}
      description="Save the exact wording and where each answer applies, including degree dropdown choices and role-specific answers. Leave the requisition blank to cover all roles at that employer. Keep your actual degree unchanged. Existing employer notes are below."
      addLabel="Add employer answer" removeLabel="Remove employer answer"
      create={() => ({ employer: "", requisition: "", country: "", timeframe: "", question: "", answer: null, category: "general", confirmedOn: "" })}
      onChange={(employerAnswers) => onChange({ employerAnswers })} />
  </>;
}
