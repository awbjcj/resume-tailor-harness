import { useId, useRef, useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { TagListInput } from "@/components/ui/tag-list-input";
import { DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { invalidateBoardQueries } from "@/features/board/query-invalidation";
import type { manualJobEn } from "@/i18n/manual-job";

type FieldName = keyof typeof manualJobEn.fields;
type ListField = "location" | "techStack" | "mustHaveSkills" | "niceToHaveSkills";
type TextField = Exclude<FieldName, ListField>;
type Option = keyof typeof manualJobEn.options;
type Values = Partial<Record<TextField, string>>;
type Details = components["schemas"]["ManualJobDetails"];

function validLink(value: string) {
  if (!value) return true;
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) && !!url.hostname && !url.username && !url.password && !/\s/.test(value);
  } catch { return false; }
}

export default function ManualJobForm({ onClose, onBusyChange }: { onClose: () => void; onBusyChange: (busy: boolean) => void }) {
  const { t } = useTranslation();
  const id = useId();
  const queryClient = useQueryClient();
  const [values, setValues] = useState<Values>({});
  const [lists, setLists] = useState<Partial<Record<ListField, string[]>>>({});
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const submitting = useRef(false);
  const [saved, setSaved] = useState<{ id: number; title: string; company: string } | null>(null);

  const field = (name: TextField, type = "text", required = false) => (
    <label className="grid min-w-0 gap-1.5 text-sm" htmlFor={`${id}-${name}`} key={name}>
      {t(`manualJob.fields.${name}`)}
      <Input id={`${id}-${name}`} name={name} type={type} required={required}
        value={values[name] ?? ""} maxLength={type === "url" ? 4096 : 1000}
        min={type === "number" ? 0 : undefined} max={name === "yoeMin" ? 100 : undefined}
        step={name === "yoeMin" ? 1 : type === "number" ? "any" : undefined}
        onChange={(event) => setValues({ ...values, [name]: event.target.value })} />
    </label>
  );
  const select = (name: TextField, options: Option[]) => (
    <label className="grid min-w-0 gap-1.5 text-sm" htmlFor={`${id}-${name}`} key={name}>
      {t(`manualJob.fields.${name}`)}
      <select id={`${id}-${name}`} name={name} value={values[name] ?? ""}
        className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
        onChange={(event) => setValues({ ...values, [name]: event.target.value })}>
        <option value="">{t("manualJob.unknown")}</option>
        {options.map((option) => <option key={option} value={option}>{t(`manualJob.options.${option}`)}</option>)}
      </select>
    </label>
  );
  const tagField = (name: ListField) => (
    <TagListInput
      id={`${id}-${name}`}
      label={t(`manualJob.fields.${name}`)}
      value={lists[name] ?? []}
      onChange={(next) => setLists((current) => ({ ...current, [name]: next }))}
      separator={name === "location" ? "semicolon" : "newline"}
      disabled={saving}
    />
  );

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting.current) return;
    setError("");
    const text = (name: TextField) => values[name]?.trim() || null;
    const number = (name: TextField) => text(name) === null ? null : Number(text(name));
    if (!text("title") || !text("company") || !text("jdText")) {
      setError(t("manualJob.required")); return;
    }
    if (![text("url"), text("applicationUrl")].every((url) => validLink(url ?? ""))) {
      setError(t("manualJob.invalidUrl")); return;
    }
    const minimum = number("salaryMin");
    const maximum = number("salaryMax");
    const currency = text("salaryCurrency")?.toUpperCase() || null;
    if ((minimum !== null || maximum !== null) && (
      !currency || !/^[A-Z]{3}$/.test(currency) || !text("salaryPeriod") ||
      (minimum !== null && (!Number.isFinite(minimum) || minimum < 0)) ||
      (maximum !== null && (!Number.isFinite(maximum) || maximum < 0)) ||
      (minimum !== null && maximum !== null && minimum > maximum)
    )) { setError(t("manualJob.invalidSalary")); return; }

    const details: Details = {
      remotePolicy: text("remotePolicy") as Details["remotePolicy"],
      seniority: text("seniority") as Details["seniority"],
      employmentType: text("employmentType") as Details["employmentType"],
      sponsorshipSignal: text("sponsorshipSignal") as Details["sponsorshipSignal"],
      remoteRestrictions: text("remoteRestrictions"), attendance: text("attendance"),
      industry: text("industry"), companySize: text("companySize"), yoeMin: number("yoeMin"),
      techStack: lists.techStack ?? [], mustHaveSkills: lists.mustHaveSkills ?? [], niceToHaveSkills: lists.niceToHaveSkills ?? [],
      salaryMin: minimum, salaryMax: maximum, salaryCurrency: currency,
      salaryPeriod: text("salaryPeriod") as Details["salaryPeriod"],
      postingId: text("postingId"), closesAt: text("closesAt"), applicationUrl: text("applicationUrl"),
    };
    submitting.current = true;
    setSaving(true); onBusyChange(true);
    try {
      const result = await api.POST("/api/jobs", { body: {
        title: text("title"), company: text("company"), jdText: text("jdText")!,
        url: text("url"), location: lists.location?.join("; ") || null,
        postedAt: text("postedAt") ? `${text("postedAt")}T00:00:00Z` : null, details,
      } });
      if (!result.data) {
        setError(t(result.response.status === 409 ? "manualJob.duplicate" : result.response.status === 429 ? "manualJob.quota" : result.response.status === 422 ? "manualJob.invalid" : "manualJob.failed"));
        return;
      }
      setSaved({ id: result.data.id, title: result.data.title ?? text("title")!, company: result.data.company ?? text("company")! });
      setValues({});
      setLists({});
      // Saving succeeded even if an unrelated board refetch fails.
      void invalidateBoardQueries(queryClient);
      void queryClient.invalidateQueries({ queryKey: ["dashboard-summary"] });
    } catch { setError(t("manualJob.failed")); }
    finally { submitting.current = false; setSaving(false); onBusyChange(false); }
  }

  return (
      <DialogContent className="sm:max-w-3xl" showCloseButton={!saving}>
        <DialogHeader>
          <DialogTitle>{t("manualJob.title")}</DialogTitle>
          <DialogDescription>{t("manualJob.description")}</DialogDescription>
        </DialogHeader>
        {saved ? <div className="space-y-4">
          <p role="status">{t("manualJob.saved", saved)}</p>
          <p className="text-sm text-muted-foreground">{t("manualJob.saveHelp")}</p>
          <a className="inline-block text-sm font-medium underline" href={`/triage?job=${saved.id}`}>{t("manualJob.view")}</a>
          <DialogFooter>
            <Button variant="outline" onClick={() => setSaved(null)}>{t("manualJob.another")}</Button>
            <Button onClick={() => { onClose(); setSaved(null); }}>{t("manualJob.done")}</Button>
          </DialogFooter>
        </div> : <form onSubmit={(event) => void submit(event)} aria-busy={saving}>
          <fieldset disabled={saving} className="space-y-6">
            <fieldset className="space-y-3">
              <legend className="mb-3 text-sm font-semibold">{t("manualJob.basics")}</legend>
              <div className="grid gap-3 sm:grid-cols-2">{field("title", "text", true)}{field("company", "text", true)}</div>
              {tagField("location")}
              <label className="grid gap-1.5 text-sm" htmlFor={`${id}-jdText`}>
                {t("manualJob.fields.jdText")}
                <textarea
                  id={`${id}-jdText`} name="jdText" required rows={9} maxLength={2_000_000}
                  value={values.jdText ?? ""}
                  className="w-full resize-y rounded-md border border-input bg-background p-3 text-sm focus-visible:outline-2 focus-visible:outline-ring"
                  onChange={(event) => setValues({ ...values, jdText: event.target.value })}
                />
              </label>
            </fieldset>
            <fieldset className="grid gap-3 sm:grid-cols-2">
              <legend className="mb-3 text-sm font-semibold">{t("manualJob.links")}</legend>
              {field("url", "url")}{field("applicationUrl", "url")}{field("postingId")}
              {field("postedAt", "date")}{field("closesAt", "date")}
            </fieldset>
            <fieldset className="grid gap-3 sm:grid-cols-2">
              <legend className="mb-3 text-sm font-semibold">{t("manualJob.work")}</legend>
              {select("remotePolicy", ["remote", "hybrid", "onsite"])}
              {select("employmentType", ["full_time", "part_time", "contract", "internship"])}
              {select("seniority", ["junior", "mid", "senior", "staff", "principal"])}
              {select("sponsorshipSignal", ["offered", "denied", "silent"])}
              {field("remoteRestrictions")}{field("attendance")}{field("industry")}{field("companySize")}{field("yoeMin", "number")}
              <p className="text-sm text-muted-foreground sm:col-span-2">{t("manualJob.listHelp")}</p>
              {tagField("techStack")}{tagField("mustHaveSkills")}{tagField("niceToHaveSkills")}
            </fieldset>
            <fieldset className="grid gap-3 sm:grid-cols-2">
              <legend className="mb-3 text-sm font-semibold">{t("manualJob.salary")}</legend>
              <p className="text-sm text-muted-foreground sm:col-span-2">{t("manualJob.salaryHelp")}</p>
              {field("salaryMin", "number")}{field("salaryMax", "number")}{field("salaryCurrency")}
              {select("salaryPeriod", ["year", "month", "week", "day", "hour"])}
            </fieldset>
            <p className="text-sm text-muted-foreground">{t("manualJob.saveHelp")}</p>
            {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onClose()}>{t("manualJob.cancel")}</Button>
              <Button type="submit" disabled={saving}>{saving && <Spinner data-icon="inline-start" />}{t(saving ? "manualJob.saving" : "manualJob.save")}</Button>
            </DialogFooter>
          </fieldset>
        </form>}
      </DialogContent>
  );
}
