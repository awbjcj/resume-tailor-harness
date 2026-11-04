export function MetricRow({ items }: { items: [string, string][] }) {
  return (
    <dl className="mb-6 flex flex-wrap gap-x-8 gap-y-4 py-4">
      {items.map(([label, value]) => (
        <div key={label} className="flex min-w-0 flex-col gap-1">
          <dt className="text-sm text-muted-foreground">{label}</dt>
          <dd className="text-2xl font-semibold leading-tight tracking-[-0.02em] tabular-nums">{value}</dd>
        </div>
      ))}
    </dl>
  );
}
