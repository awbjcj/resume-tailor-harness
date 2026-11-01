import { useReviewValueCopy } from "@/i18n/review-fields";
import { cn } from "@/lib/utils";

export function ReviewValue({ value, hiddenFields, field, owner }: { value: unknown; hiddenFields?: ReadonlySet<string>; field?: string; owner?: string }) {
  const copy = useReviewValueCopy();
  if (value == null) return <span className="text-muted-foreground">{copy.none}</span>;
  if (value === "") return <span className="text-muted-foreground">{copy.emptyText}</span>;
  if (typeof value === "boolean") return <span>{value ? copy.yes : copy.no}</span>;
  if (Array.isArray(value)) {
    return value.length ? <ul className="min-w-0 space-y-3 border-l pl-3">{value.map((item, index) => (
      <li key={index} className="min-w-0"><ReviewValue value={item} hiddenFields={hiddenFields} field={field} owner={owner} /></li>
    ))}</ul> : <span className="text-muted-foreground">{copy.emptyList}</span>;
  }
  if (typeof value === "object") {
    const entries = Object.entries(value).filter(([key]) => !hiddenFields?.has(key));
    return entries.length ? <dl className="min-w-0 space-y-3">{entries.map(([key, item]) => (
      <div key={key} className="min-w-0 space-y-1">
        <dt className="text-xs font-medium leading-relaxed text-muted-foreground [overflow-wrap:anywhere]">{copy.field(key, owner)}</dt>
        <dd className="min-w-0 whitespace-pre-wrap leading-relaxed [overflow-wrap:anywhere]"><ReviewValue value={item} hiddenFields={hiddenFields} field={key} owner={copy.normalizeField(key)} /></dd>
      </div>
    ))}</dl> : <span className="text-muted-foreground">{copy.noFields}</span>;
  }
  return <span className="whitespace-pre-wrap leading-relaxed [overflow-wrap:anywhere]">{typeof value === "string" ? copy.enumValue(value, field) : String(value)}</span>;
}

export function ChangePreview({ before, after, hiddenFields, entity }: {
  before: unknown;
  after: unknown;
  hiddenFields?: ReadonlySet<string>;
  entity?: string;
}) {
  const copy = useReviewValueCopy();
  const single = before == null || after == null;
  const sides = before == null && after != null ? [[copy.newItem, after]]
    : after == null && before != null ? [[copy.removedItem, before]]
      : [[copy.before, before], [copy.after, after]];
  return (
    <div className={cn("grid min-w-0 gap-3 text-sm", !single && "@lg/review:grid-cols-2")}>
      {sides.map(([label, value], index) => (
        <div key={index} className={cn("min-w-0 space-y-3 rounded-lg border p-3 sm:p-4", !single && index === 0 ? "bg-muted/25" : "bg-background/60")}>
          <p className="text-xs font-semibold text-muted-foreground">{String(label)}</p>
          <ReviewValue value={value} hiddenFields={hiddenFields} owner={entity} />
        </div>
      ))}
    </div>
  );
}
