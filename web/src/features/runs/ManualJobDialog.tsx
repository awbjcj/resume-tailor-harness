import { useId, useRef, useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { PenLine } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { invalidateBoardQueries } from "@/features/board/query-invalidation";
import type { manualJobEn } from "@/i18n/manual-job";

type FieldName = keyof typeof manualJobEn.fields;
type Option = keyof typeof manualJobEn.options;
type Values = Partial<Record<FieldName, string>>;
type Details = components["schemas"]["ManualJobDetails"];

function validLink(value: string) {
  if (!value) return true;
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) && !!url.hostname && !url.username && !url.password && !/\s/.test(value);
  } catch { return false; }
}

export function ManualJobDialog() {
  const { t } = useTranslation();
  const id = useId();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [values, setValues] = useState<Values>({});
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const submitting = useRef(false);
  const [saved, setSaved] = useState<{ id: number; title: string; company: string } | null>(null);

  const field = (name: FieldName, type = "text", required = false) => (
    <label className="grid min-w-0 gap-1.5 text-sm" htmlFor={`${id}-${name}`} key={name}>
      {t(`manualJob.fields.${name}`)}
      <Input id={`${id}-${name}`} name={name} type={type} required={required}
        value={values[name] ?? ""} maxLength={name === "location" ? 4000 : type === "url" ? 4096 : 1000}
        min={type === "number" ? 0 : undefined} max={name === "yoeMin" ? 100 : undefined}
        step={name === "yoeMin" ? 1 : type === "number" ? "any" : undefined}
        onChange={(event) => setValues({ ...values, [name]: event.target.value })} />
    </label>
  );
  const select = (name: FieldName, options: Option[]) => (
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
  const textarea = (name: FieldName, required = false) => (
    <label className="grid gap-1.5 text-sm" htmlFor={`${id}-${name}`} key={name}>
      {t(`manualJob.fields.${name}`)}
      <textarea id={`${id}-${name}`} name={name} required={required} rows={required ? 9 : 3}
        maxLength={required ? 2_000_000 : 40000} value={values[name] ?? ""}
        aria-describedby={required ? undefined : `${id}-list-help`}
        className="w-full resize-y rounded-md border border-input bg-background p-3 text-sm focus-visible:outline-2 focus-visible:outline-ring"
        onChange={(event) => setValues({ ...values, [name]: event.target.value })} />
    </label>
  );

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting.current) return;
    setError("");
    const text = (name: FieldName) => values[name]?.trim() || null;
    const number = (name: FieldName) => text(name) === null ? null : Number(text(name));
    const list = (name: FieldName) => (text(name) ?? "").split(/\r?\n/).map((item) => item.trim()).filter(Boolean);
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
      techStack: list("techStack"), mustHaveSkills: list("mustHaveSkills"), niceToHaveSkills: list("niceToHaveSkills"),
      salaryMin: minimum, salaryMax: maximum, salaryCurrency: currency,
      salaryPeriod: text("salaryPeriod") as Details["salaryPeriod"],
      postingId: text("postingId"), closesAt: text("closesAt"), applicationUrl: text("applicationUrl"),
    };
    submitting.current = true;
    setSaving(true);
    try {
      const result = await api.POST("/api/jobs", { body: {
        title: text("title"), company: text("company"), jdText: text("jdText")!,
        url: text("url"), location: text("location"),
        postedAt: text("postedAt") ? `${text("postedAt")}T00:00:00Z` : null, details,
      } });
      if (!result.data) {
        setError(t(result.response.status === 409 ? "manualJob.duplicate" : result.response.status === 429 ? "manualJob.quota" : result.response.status === 422 ? "manualJob.invalid" : "manualJob.failed"));
        return;
      }
      setSaved({ id: result.data.id, title: result.data.title ?? text("title")!, company: result.data.company ?? text("company")! });
      setValues({});
      // Saving succeeded even if an unrelated board refetch fails.
      void invalidateBoardQueries(queryClient);
      void queryClient.invalidateQueries({ queryKey: ["dashboard-summary"] });
    } catch { setError(t("manualJob.failed")); }
    finally { submitting.current = false; setSaving(false); }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => { if (!submitting.current) setOpen(next); }}>
      <DialogTrigger render={<Button size="sm" variant="outline" />}>
        <PenLine data-icon="inline-start" aria-hidden="true" />{t("manualJob.title")}
      </DialogTrigger>
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
            <Button onClick={() => { setOpen(false); setSaved(null); }}>{t("manualJob.done")}</Button>
          </DialogFooter>
        </div> : <form onSubmit={(event) => void submit(event)} aria-busy={saving}>
          <fieldset disabled={saving} className="space-y-6">
            <fieldset className="space-y-3">
              <legend className="mb-3 text-sm font-semibold">{t("manualJob.basics")}</legend>
              <div className="grid gap-3 sm:grid-cols-2">{field("title", "text", true)}{field("company", "text", true)}</div>
              {field("location")}{textarea("jdText", true)}
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
              <p className="text-sm text-muted-foreground sm:col-span-2" id={`${id}-list-help`}>{t("manualJob.listHelp")}</p>
              {textarea("techStack")}{textarea("mustHaveSkills")}{textarea("niceToHaveSkills")}
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
              <Button type="button" variant="outline" onClick={() => setOpen(false)}>{t("manualJob.cancel")}</Button>
              <Button type="submit" disabled={saving}>{saving && <Spinner data-icon="inline-start" />}{t(saving ? "manualJob.saving" : "manualJob.save")}</Button>
            </DialogFooter>
          </fieldset>
        </form>}
      </DialogContent>
    </Dialog>
  );
}
