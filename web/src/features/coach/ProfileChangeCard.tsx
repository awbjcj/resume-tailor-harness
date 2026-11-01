import { useTranslation } from "react-i18next";
import "@/i18n/profile-changes";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import type { CoachChangeDraft } from "./use-coach";

const INTERNAL_FIELDS = new Set([
  "id", "source", "source_ref", "schema_version", "synthesized", "inferred",
  "evidence_fact_ids", "github_profile", "extra",
]);

function Value({ value }: { value: unknown }) {
  const { t } = useTranslation();
  if (value == null || value === "") return <span className="text-muted-foreground">{t("profileChanges.empty")}</span>;
  if (typeof value === "boolean") return <>{t(value ? "profileChanges.yes" : "profileChanges.no")}</>;
  if (Array.isArray(value)) {
    return value.length ? <ul className="space-y-1">{value.map((item, index) => <li key={index}><Value value={item} /></li>)}</ul> : <Value value={null} />;
  }
  if (typeof value === "object") {
    return <dl className="space-y-2">{Object.entries(value).filter(([key]) => !INTERNAL_FIELDS.has(key)).map(([key, item]) => (
      <div key={key} className="min-w-0">
        <dt className="text-xs font-medium text-muted-foreground">{t(`profileChanges.fields.${key}`, { defaultValue: key.replaceAll("_", " ") })}</dt>
        <dd className="min-w-0 whitespace-pre-wrap [overflow-wrap:anywhere]"><Value value={item} /></dd>
      </div>
    ))}</dl>;
  }
  return <>{String(value)}</>;
}

export function ProfileChangeCard({ draft, busy, onResolve }: {
  draft: CoachChangeDraft;
  busy: boolean;
  onResolve: (decision: "apply" | "discard") => void;
}) {
  const { t } = useTranslation();
  const pending = draft.status === "pending";
  return <Card className="min-w-0 rounded-2xl border-primary/25">
    <CardHeader>
      <CardTitle className="flex min-w-0 flex-col items-start gap-2 text-base sm:flex-row">
        <span className="w-full min-w-0 flex-1 [overflow-wrap:anywhere] sm:w-auto">{draft.title}</span>
        <Badge variant="secondary">{t(`profileChanges.${draft.status}`)}</Badge>
      </CardTitle>
      <CardDescription>{t("profileChanges.help")}</CardDescription>
    </CardHeader>
    <CardContent className="min-w-0 space-y-4">
      {(draft.previews ?? []).map((preview, index) => <section key={index} className="min-w-0 space-y-2">
        <h3 className="text-sm font-semibold">{t(`profileChanges.operations.${preview.operation}`, { defaultValue: "" })} {t(`profileChanges.fields.${preview.entity}`, { defaultValue: preview.label })}</h3>
        {preview.entity === "profile" && preview.operation === "delete" ? <p className="text-sm text-muted-foreground">{t("profileChanges.removalHelp")}</p> : null}
        <div className="grid min-w-0 gap-3 sm:grid-cols-2">
          {Object.entries({ before: preview.before, after: preview.after }).map(([side, value]) => <div key={side} className="min-w-0 rounded-xl border bg-muted/20 p-3 text-sm">
            <p className="mb-2 font-medium">{t(`profileChanges.${side}`, { defaultValue: side })}</p>
            <Value value={value} />
          </div>)}
        </div>
      </section>)}
      <div className="space-y-2">
        <p className="text-xs font-medium text-muted-foreground">{t("profileChanges.evidence")}</p>
        {(draft.quotes ?? []).map((quote, index) => <blockquote key={index} className="border-l-2 pl-3 text-sm [overflow-wrap:anywhere]">{quote}</blockquote>)}
      </div>
    </CardContent>
    {pending ? <CardFooter className="flex flex-wrap gap-2">
      <Button size="sm" disabled={busy} onClick={() => onResolve("apply")}>{t("profileChanges.apply")}</Button>
      <Button size="sm" variant="outline" disabled={busy} onClick={() => onResolve("discard")}>{t("profileChanges.discard")}</Button>
    </CardFooter> : null}
  </Card>;
}
